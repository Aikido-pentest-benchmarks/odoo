# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import datetime
import hashlib
import hmac
import json
import logging
import odoo
import re
import werkzeug

from odoo import _, http
from odoo.http import request
from werkzeug.exceptions import NotFound, BadRequest

_logger = logging.getLogger(__name__)

# Allowed redirect URI patterns for mail plugin OAuth flow
# These patterns are designed to match legitimate mail plugin clients
ALLOWED_REDIRECT_PATTERNS = [
    # Localhost for development (any port)
    re.compile(r'^https?://localhost(:[0-9]+)?(/.*)?$'),
    re.compile(r'^https?://127\.0\.0\.1(:[0-9]+)?(/.*)?$'),
    re.compile(r'^https?://\[::1\](:[0-9]+)?(/.*)?$'),
    # Outlook add-in callback patterns
    re.compile(r'^https://outlook\.office\.com/.*$'),
    re.compile(r'^https://outlook\.office365\.com/.*$'),
    re.compile(r'^https://outlook\.live\.com/.*$'),
    # Gmail add-on callback patterns  
    re.compile(r'^https://mail\.google\.com/.*$'),
]


class Authenticate(http.Controller):

    @http.route(['/mail_client_extension/auth', '/mail_plugin/auth'], type='http', auth="user", methods=['GET'], website=True)
    def auth(self, **values):
        """
         Once authenticated this route renders the view that shows an app wants to access Odoo.
         The user is invited to allow or deny the app. The form posts to `/mail_client_extension/auth/confirm`.

         old route name "/mail_client_extension/auth is deprecated as of saas-14.3,it is not needed for newer
         versions of the mail plugin but necessary for supporting older versions
         """
        if not request.env.user._is_internal():
            return request.render('mail_plugin.app_error', {'error': _('Access Error: Only Internal Users can link their inboxes to this database.')})
        
        # Validate redirect URI before rendering the consent page
        redirect_uri = values.get('redirect', '')
        if redirect_uri and not self._is_redirect_uri_allowed(redirect_uri):
            _logger.warning('Rejected unauthorized redirect_uri in auth request: %s', redirect_uri)
            return request.render('mail_plugin.app_error', {'error': _('Invalid redirect URI. Please contact your administrator.')})
        
        return request.render('mail_plugin.app_auth', values)

    def _is_redirect_uri_allowed(self, redirect_uri):
        """
        Validate that the redirect URI matches one of the allowed patterns.
        This prevents authorization code exfiltration to arbitrary external domains.
        
        :param str redirect_uri: The redirect URI to validate
        :return: True if the URI is allowed, False otherwise
        """
        if not redirect_uri:
            return False
        
        # Check against allowed patterns
        for pattern in ALLOWED_REDIRECT_PATTERNS:
            if pattern.match(redirect_uri):
                return True
        
        # Check if it's a custom system parameter (for extensibility)
        custom_patterns = request.env['ir.config_parameter'].sudo().get_param(
            'mail_plugin.allowed_redirect_uris', ''
        )
        if custom_patterns:
            for custom_uri in custom_patterns.split(','):
                custom_uri = custom_uri.strip()
                if custom_uri and redirect_uri.startswith(custom_uri):
                    return True
        
        return False

    @http.route(['/mail_client_extension/auth/confirm', '/mail_plugin/auth/confirm'], type='http', auth="user", methods=['POST'])
    def auth_confirm(self, scope, friendlyname, redirect, info=None, do=None, **kw):
        """
        Called by the `app_auth` template. If the user decided to allow the app to access Odoo, a temporary auth code
        is generated and they are redirected to `redirect` with this code in the URL. It should redirect to the app, and
        the app should then exchange this auth code for an access token by calling
        `/mail_client/auth/access_token`.

        old route name "/mail_client_extension/auth/confirm is deprecated as of saas-14.3,it is not needed for newer
        versions of the mail plugin but necessary for supporting older versions
        """
        # Validate redirect URI to prevent authorization code exfiltration
        if not self._is_redirect_uri_allowed(redirect):
            _logger.warning('Rejected unauthorized redirect_uri in auth_confirm: %s for user %s', 
                          redirect, request.env.user.login)
            return request.render('mail_plugin.app_error', {
                'error': _('Invalid redirect URI. Authorization denied for security reasons.')
            })
        
        parsed_redirect = werkzeug.urls.url_parse(redirect)
        params = parsed_redirect.decode_query()
        if do:
            name = friendlyname if not info else f'{friendlyname}: {info}'
            # Include redirect URI in the auth code for binding validation during token exchange
            auth_code = self._generate_auth_code(scope, name, redirect)
            # params is a MultiDict which does not support .update() with kwargs
            # the state attribute is needed for the gmail connector
            params.update({'success': 1, 'auth_code': auth_code, 'state': kw.get('state', '')})
        else:
            params.update({'success': 0, 'state': kw.get('state', '')})
        updated_redirect = parsed_redirect.replace(query=werkzeug.urls.url_encode(params))
        return request.redirect(updated_redirect.to_url(), local=False)

    @http.route(['/mail_plugin/auth/check_version'], type='jsonrpc', auth="none", cors="*",
                methods=['POST', 'OPTIONS'])
    def auth_check_version(self):
        """Allow to know if the module is installed and which addin version is supported."""
        return 1

    # In this case, an exception will be thrown in case of preflight request if only POST is allowed.
    @http.route(['/mail_client_extension/auth/access_token', '/mail_plugin/auth/access_token'], type='jsonrpc', auth="none", cors="*",
                methods=['POST', 'OPTIONS'])
    def auth_access_token(self, auth_code='', redirect_uri='', **kw):
        """
        Called by the external app to exchange an auth code, which is temporary and was passed in a URL, for an
        access token, which is permanent, and can be used in the `Authorization` header to authorize subsequent requests

        old route name "/mail_client_extension/auth/access_token is deprecated as of saas-14.3,it is not needed for newer
        versions of the mail plugin but necessary for supporting older versions
        """
        if not auth_code:
            return {"error": "Invalid code"}
        
        # Validate and parse the auth code
        auth_message = self._get_auth_code_data(auth_code)
        if not auth_message:
            return {"error": "Invalid code"}
        
        # Verify redirect_uri binding to prevent code exfiltration attacks
        code_redirect_uri = auth_message.get('redirect_uri', '')
        if code_redirect_uri != redirect_uri:
            _logger.warning(
                'Authorization code redirect_uri mismatch: expected %s, got %s for user %s',
                code_redirect_uri, redirect_uri, auth_message.get('uid')
            )
            return {"error": "Invalid code"}
        
        # Check for code replay attacks using a nonce-based tracking mechanism
        code_hash = self._get_code_hash(auth_code)
        if self._is_code_used(code_hash):
            _logger.warning(
                'Authorization code replay attempt detected for user %s',
                auth_message.get('uid')
            )
            return {"error": "Invalid code"}
        
        # Mark code as used before generating token to prevent race conditions
        self._mark_code_used(code_hash)
        
        request.update_env(user=auth_message['uid'])
        scope = 'odoo.plugin.' + auth_message.get('scope', '')
        api_key = request.env['res.users.apikeys']._generate(
            scope,
            auth_message['name'],
            datetime.datetime.now() + datetime.timedelta(days=1)
        )
        return {'access_token': api_key}

    def _get_code_hash(self, auth_code):
        """Generate a hash of the auth code for tracking usage."""
        return hashlib.sha256(auth_code.encode()).hexdigest()

    def _is_code_used(self, code_hash):
        """
        Check if an authorization code has already been used.
        Uses dedicated model to track used codes within their validity window.
        """
        # Use sudo to bypass access rights since this is called from auth="none" endpoint
        return bool(request.env['mail_plugin.auth_code'].sudo().search_count([
            ('code_hash', '=', code_hash)
        ], limit=1))

    def _mark_code_used(self, code_hash):
        """
        Mark an authorization code as used to prevent replay attacks.
        Stores the code hash with automatic expiration via autovacuum.
        """
        try:
            # Use sudo to bypass access rights since this is called from auth="none" endpoint
            request.env['mail_plugin.auth_code'].sudo().create({
                'code_hash': code_hash
            })
        except Exception as e:
            # If there's a unique constraint violation, the code was already used
            _logger.warning('Failed to mark auth code as used (likely already used): %s', e)
            # Re-raise to ensure the token exchange fails
            raise

    def _get_auth_code_data(self, auth_code):
        try:
            data, auth_code_signature = auth_code.split('.')
            data = base64.b64decode(data)
            auth_code_signature = base64.b64decode(auth_code_signature)
        except (ValueError, Exception) as e:
            _logger.warning('Malformed auth code: %s', e)
            return None
        
        signature = odoo.tools.misc.hmac(request.env(su=True), 'mail_plugin', data).encode()
        if not hmac.compare_digest(auth_code_signature, signature):
            return None

        auth_message = json.loads(data)
        # Check the expiration - reduced to 1 minute for better security
        if datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(auth_message['timestamp']) > datetime.timedelta(
                minutes=1):
            return None

        return auth_message

    # Using UTC explicitly in case of a distributed system where the generation and the signature verification do not
    # necessarily happen on the same server
    def _generate_auth_code(self, scope, name, redirect_uri):
        if not request.env.user._is_internal():
            raise NotFound()
        auth_dict = {
            'scope': scope,
            'name': name,
            'timestamp': int(datetime.datetime.utcnow().timestamp()),
            # <- elapsed time should be < 1 min when verifying (reduced from 3 mins)
            'uid': request.env.uid,
            'redirect_uri': redirect_uri,  # Bind code to specific redirect URI
        }
        auth_message = json.dumps(auth_dict, sort_keys=True).encode()
        signature = odoo.tools.misc.hmac(request.env(su=True), 'mail_plugin', auth_message).encode()
        auth_code = "%s.%s" % (base64.b64encode(auth_message).decode(), base64.b64encode(signature).decode())
        _logger.info('Auth code created - user %s, scope %s, redirect_uri %s', request.env.user, scope, redirect_uri)
        return auth_code

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch

from werkzeug.exceptions import Forbidden

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment_nuvei.controllers.main import NuveiController
from odoo.addons.payment_nuvei.tests.common import NuveiCommon


@tagged('post_install', '-at_install')
class TestProcessingFlows(NuveiCommon):

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_redirect_notification_triggers_processing(self):
        """ Test that receiving a redirect notification triggers the processing of the notification
        data. """
        self._create_transaction(flow='redirect')
        url = self._build_url(NuveiController._return_url)
        with patch(
            'odoo.addons.payment_nuvei.controllers.main.NuveiController._verify_signature'
        ), patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction._process'
        ) as process_mock:
            self._make_http_get_request(url, params=self.payment_data)
            self.assertEqual(process_mock.call_count, 1)

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_webhook_notification_triggers_processing(self):
        """ Test that receiving a valid webhook notification triggers the processing of the
        payment data. """
        self._create_transaction('redirect')
        url = self._build_url(NuveiController._webhook_url)
        with patch(
            'odoo.addons.payment_nuvei.controllers.main.NuveiController._verify_signature'
        ), patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction._process'
        ) as process_mock:
            self._make_http_post_request(url, data=self.payment_data)
            self.assertEqual(process_mock.call_count, 1)

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_redirect_notification_triggers_signature_check(self):
        """ Test that receiving a redirect notification triggers a signature check. """
        self._create_transaction('redirect')
        url = self._build_url(NuveiController._return_url)
        with patch(
            'odoo.addons.payment_nuvei.controllers.main.NuveiController._verify_signature'
        ) as signature_check_mock, patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction._process'
        ):
            self._make_http_get_request(url, params=self.payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_webhook_notification_triggers_signature_check(self):
        """ Test that receiving a webhook notification triggers a signature check. """
        self._create_transaction('redirect')
        url = self._build_url(NuveiController._webhook_url)
        with patch(
            'odoo.addons.payment_nuvei.controllers.main.NuveiController._verify_signature'
        ) as signature_check_mock, patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction._process'
        ):
            self._make_http_post_request(url, data=self.payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    def test_accept_notification_with_valid_signature(self):
        """ Test the verification of a notification with a valid signature. """
        tx = self._create_transaction('redirect')
        self._assert_does_not_raise(
            Forbidden, NuveiController._verify_signature, tx, self.payment_data
        )

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_reject_notification_with_missing_signature(self):
        """ Test the verification of a notification with a missing signature. """
        tx = self._create_transaction('redirect')
        payload = dict(self.payment_data, advanceResponseChecksum=None)
        self.assertRaises(Forbidden, NuveiController._verify_signature, tx, payload)

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_reject_notification_with_invalid_signature(self):
        """ Test the verification of a notification with an invalid signature. """
        tx = self._create_transaction('redirect')
        payload = dict(self.payment_data, advanceResponseChecksum='dummy')
        self.assertRaises(Forbidden, NuveiController._verify_signature, tx, payload)

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_reject_success_status_with_error_access_token(self):
        """ Test that a success status with error_access_token is rejected to prevent forgery. """
        tx = self._create_transaction('redirect')
        # Attempt to forge a successful payment using error_access_token
        payload = dict(self.payment_data, Status='APPROVED')
        error_token = self._generate_test_access_token(tx.reference)
        self.assertRaises(
            Forbidden, NuveiController._verify_signature, tx, payload, error_access_token=error_token
        )

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_reject_ok_status_with_error_access_token(self):
        """ Test that an 'ok' status with error_access_token is rejected to prevent forgery. """
        tx = self._create_transaction('redirect')
        # Attempt to forge a successful payment using error_access_token with 'ok' status
        payload = dict(self.payment_data, ppp_status='ok')
        error_token = self._generate_test_access_token(tx.reference)
        self.assertRaises(
            Forbidden, NuveiController._verify_signature, tx, payload, error_access_token=error_token
        )

    def test_accept_error_status_with_valid_error_access_token(self):
        """ Test that an error status with valid error_access_token is accepted. """
        tx = self._create_transaction('redirect')
        payload = {'Status': 'ERROR', 'Reason': 'Payment declined'}
        error_token = self._generate_test_access_token(tx.reference)
        self._assert_does_not_raise(
            Forbidden, NuveiController._verify_signature, tx, payload, error_access_token=error_token
        )

    def test_accept_pending_status_with_valid_error_access_token(self):
        """ Test that a pending status with valid error_access_token is accepted. """
        tx = self._create_transaction('redirect')
        payload = {'Status': 'PENDING'}
        error_token = self._generate_test_access_token(tx.reference)
        self._assert_does_not_raise(
            Forbidden, NuveiController._verify_signature, tx, payload, error_access_token=error_token
        )

    @mute_logger('odoo.addons.payment_nuvei.controllers.main')
    def test_reject_error_status_with_invalid_error_access_token(self):
        """ Test that an error status with invalid error_access_token is rejected. """
        tx = self._create_transaction('redirect')
        payload = {'Status': 'ERROR', 'Reason': 'Payment declined'}
        self.assertRaises(
            Forbidden, NuveiController._verify_signature, tx, payload, error_access_token='invalid'
        )

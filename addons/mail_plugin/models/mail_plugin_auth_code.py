# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MailPluginAuthCode(models.Model):
    """
    Tracks used authorization codes to prevent replay attacks.
    Codes are stored temporarily and automatically cleaned up.
    """

    _name = "mail_plugin.auth_code"
    _description = "Mail Plugin Used Authorization Codes"
    _rec_name = "code_hash"
    _order = "create_date desc"

    code_hash = fields.Char(
        string="Code Hash", required=True, index=True, readonly=True
    )
    create_date = fields.Datetime(string="Used At", readonly=True, index=True)

    _sql_constraints = [
        (
            "code_hash_unique",
            "UNIQUE(code_hash)",
            "This authorization code has already been used.",
        )
    ]

    @api.autovacuum
    def _gc_used_auth_codes(self):
        """
        Garbage collect used authorization codes older than 5 minutes.
        Called automatically by the autovacuum system.
        """
        self.env.cr.execute("""
            DELETE FROM mail_plugin_auth_code
            WHERE create_date < (now() at time zone 'utc' - interval '5 minutes')
        """)
        if self.env.cr.rowcount:
            _logger.info(
                "GC'd %d expired mail_plugin authorization codes", self.env.cr.rowcount
            )

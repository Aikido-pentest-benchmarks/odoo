# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class PosPayment(models.Model):
    _inherit = "pos.payment"

    _sql_constraints = [
        (
            "unique_pine_labs_plutus_transaction_ref",
            "UNIQUE(pine_labs_plutus_transaction_ref)",
            "A payment with this Pine Labs transaction reference already exists. Transaction replay is not allowed.",
        )
    ]

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, models

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_custom.controllers.main import CustomController


_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return custom-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        if self.provider_code != 'custom':
            return super()._get_specific_rendering_values(processing_values)

        # Generate an access token to validate the callback authenticity
        access_token = payment_utils.generate_access_token(
            self.reference, self.amount, self.currency_id.id, self.partner_id.id
        )

        return {
            'api_url': CustomController._process_url,
            'reference': self.reference,
            'access_token': access_token,
        }

    def _get_communication(self):
        """ Return the communication the user should use for their transaction.

        This communication might change according to the settings and the accounting localization.

        Note: self.ensure_one()

        :return: The selected communication.
        :rtype: str
        """
        self.ensure_one()
        communication = ""
        if hasattr(self, 'invoice_ids') and self.invoice_ids:
            communication = self.invoice_ids[0].payment_reference
        elif hasattr(self, 'sale_order_ids') and self.sale_order_ids:
            communication = self.sale_order_ids[0].reference
        return communication or self.reference

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to skip the amount validation for custom flows."""
        if self.provider_code != 'custom':
            return super()._extract_amount_data(payment_data)
        return None

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction based on the payment data."""
        if self.provider_code != 'custom':
            return super()._apply_updates(payment_data)

        # Validate the access token to ensure the callback is authentic
        access_token = payment_data.get('access_token')
        if not payment_utils.check_access_token(
            access_token, self.reference, self.amount, self.currency_id.id, self.partner_id.id
        ):
            _logger.warning(
                "Received custom payment callback with invalid access token for transaction %s",
                self.reference
            )
            error_msg = _(
                "The payment notification could not be authenticated. "
                "Please contact us if the problem persists."
            )
            self._set_error(error_msg)
            return

        _logger.info(
            "Validated custom payment for transaction %s: set as pending.", self.reference
        )
        self._set_pending()

    def _log_received_message(self):
        """ Override of `payment` to remove custom providers from the recordset.

        :return: None
        """
        other_provider_txs = self.filtered(lambda t: t.provider_code != 'custom')
        super(PaymentTransaction, other_provider_txs)._log_received_message()

    def _get_sent_message(self):
        """ Override of payment to return a different message.

        :return: The 'transaction sent' message
        :rtype: str
        """
        message = super()._get_sent_message()
        if self.provider_code == 'custom':
            message = _(
                "The customer has selected %(provider_name)s to make the payment.",
                provider_name=self.provider_id.name
            )
        return message

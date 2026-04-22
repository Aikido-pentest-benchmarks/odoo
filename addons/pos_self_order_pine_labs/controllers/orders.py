# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http
from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController
from odoo.tools import consteq
from werkzeug.exceptions import NotFound, Unauthorized
from odoo.exceptions import MissingError


class PosSelfOrderPineLabsController(PosSelfOrderController):
    @http.route('/pos-self-order/pine-labs-fetch-payment-status/', auth='public', type='jsonrpc')
    def pine_labs_fetch_payment_status(self, access_token, order_id, payment_data, payment_method_id, order_access_token):
        pos_config = self._verify_pos_config(access_token)
        order = pos_config.env['pos.order'].browse(order_id)
        payment_method = pos_config.env['pos.payment.method'].browse(payment_method_id)

        if not order.exists() or not payment_method.exists() or order.config_id.id != pos_config.id:
            raise NotFound()

        # Verify order-specific access token to prevent cross-order payment forgery
        if not order.access_token or not consteq(order.access_token, order_access_token):
            raise MissingError(pos_config.env._("Your order does not exist or has been removed"))

        pine_labs_status_response = payment_method.pine_labs_fetch_payment_status(payment_data)
        if pine_labs_status_response.get('status') == "TXN APPROVED":
            data = pine_labs_status_response.get('data')
            plutus_transaction_ref = pine_labs_status_response.get('plutusTransactionReferenceID')
            
            # Prevent transaction replay: verify this transaction hasn't been used before
            if plutus_transaction_ref:
                existing_payment = pos_config.env['pos.payment'].sudo().search([
                    ('pine_labs_plutus_transaction_ref', '=', plutus_transaction_ref)
                ], limit=1)
                if existing_payment:
                    raise Unauthorized(pos_config.env._("This transaction has already been processed"))
            
            order.add_payment({
                'amount': order.amount_total,
                'payment_method_id': payment_method.id,
                'cardholder_name': data.get('Card Holder Name'),
                'transaction_id': data.get('TransactionLogId'),
                'payment_status': 'done',
                'pos_order_id': order.id,
                'payment_method_authcode': data.get('ApprovalCode'),
                'card_brand': data.get('Card Type'),
                'payment_method_issuer_bank': data.get('Acquirer Name'),
                'card_no': data.get('Card Number') and data.get('Card Number')[-4:],
                'payment_method_payment_mode': data.get('PaymentMode'),
                'payment_ref_no': payment_data.get('payment_ref_no'),
                'pine_labs_plutus_transaction_ref': plutus_transaction_ref,
            })
            order.action_pos_order_paid()
            order._send_payment_result('Success')
        return pine_labs_status_response

    @http.route("/pos-self-order/pine-labs-cancel-transaction/", auth="public", type="jsonrpc")
    def pine_labs_cancel_transaction(self, access_token, order_id, payment_data, payment_method_id, order_access_token):
        pos_config = self._verify_pos_config(access_token)
        order = pos_config.env['pos.order'].browse(order_id)
        payment_method = pos_config.env['pos.payment.method'].browse(payment_method_id)

        if not order.exists() or not payment_method.exists() or order.config_id.id != pos_config.id:
            raise NotFound()

        # Verify order-specific access token to prevent unauthorized cancellation
        if not order.access_token or not consteq(order.access_token, order_access_token):
            raise MissingError(pos_config.env._("Your order does not exist or has been removed"))

        return payment_method.pine_labs_cancel_payment_request(payment_data)

# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.exceptions import AccessError


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _can_bypass_rights_on_media_dialog(self, **attachment_data):
        # We need to allow and sudo the case of an "url + file" attachment,
        # which is by default forbidden for non admin.
        # See `_check_serving_attachments`
        forbidden = 'url' in attachment_data and attachment_data.get('type', 'binary') == 'binary'
        if forbidden and attachment_data['url'].startswith('/unsplash/'):
            # Verify that the user has write access to the target record before
            # allowing the bypass to prevent unauthorized attachment creation
            res_model = attachment_data.get('res_model')
            res_id = attachment_data.get('res_id')
            if res_model and res_model != 'ir.ui.view' and res_id:
                try:
                    target_record = self.env[res_model].browse(res_id).exists()
                    if not target_record:
                        return False
                    # Check if user has write access to the target record
                    target_record.check_access('write')
                except (KeyError, AccessError):
                    # Model doesn't exist or user doesn't have write access
                    return False
            return True
        return super()._can_bypass_rights_on_media_dialog(**attachment_data)

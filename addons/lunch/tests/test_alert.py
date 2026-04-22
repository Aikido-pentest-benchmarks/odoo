# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta
from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import common
from odoo.addons.lunch.tests.common import TestsCommon


class TestAlarm(TestsCommon):
    @common.users('cle-lunch-manager')
    def test_cron_sync_create(self):
        cron_ny = self.alert_ny.cron_id.sudo()
        self.assertTrue(cron_ny.active)
        self.assertEqual(cron_ny.name, "Lunch: alert chat notification (New York UTC-5)")
        self.assertEqual(
            [line for line in cron_ny.code.splitlines() if not line.lstrip().startswith("#")],
            ["env['lunch.alert'].browse([%i])._notify_chat()" % self.alert_ny.id])
        self.assertEqual(cron_ny.nextcall, datetime(2021, 1, 29, 15, 0))  # New-york is UTC-5

        tokyo_cron = self.alert_tokyo.cron_id.sudo()
        self.assertEqual(tokyo_cron.nextcall, datetime(2021, 1, 29, 23, 0))  # Tokyo is UTC+9 but the cron is posponed

    @common.users('cle-lunch-manager')
    def test_cron_sync_active(self):
        cron_ny = self.alert_ny.cron_id.sudo()

        self.alert_ny.active = False
        self.assertFalse(cron_ny.active)
        self.alert_ny.active = True
        self.assertTrue(cron_ny.active)

        self.alert_ny.mode = 'alert'
        self.assertFalse(cron_ny.active)
        self.alert_ny.mode = 'chat'
        self.assertTrue(cron_ny.active)

        ctx_today = fields.Date.context_today(self.alert_ny, self.fakenow)
        self.alert_ny.until = ctx_today - timedelta(days=1)
        self.assertFalse(cron_ny.active)
        self.alert_ny.until = ctx_today + timedelta(days=2)
        self.assertTrue(cron_ny.active)
        self.alert_ny.until = False
        self.assertTrue(cron_ny.active)

    @common.users('cle-lunch-manager')
    def test_cron_sync_nextcall(self):
        cron_ny = self.alert_ny.cron_id.sudo()
        old_nextcall = cron_ny.nextcall

        self.alert_ny.notification_time -= 5
        self.assertEqual(cron_ny.nextcall, old_nextcall - timedelta(hours=5) + timedelta(days=1))

        # Simulate cron execution
        cron_ny.lastcall = old_nextcall - timedelta(hours=5)
        cron_ny.nextcall += timedelta(days=1)

        self.alert_ny.notification_time += 7
        self.assertEqual(cron_ny.nextcall, old_nextcall + timedelta(days=1, hours=2))

        self.alert_ny.notification_time -= 1
        self.assertEqual(cron_ny.nextcall, old_nextcall + timedelta(days=1, hours=1))

    @common.users('cle-lunch-manager')
    def test_cron_rebinding_prevention(self):
        """Test that cron_id cannot be rebound to arbitrary scheduled actions."""
        # Create an arbitrary cron that doesn't belong to this alert
        arbitrary_cron = self.env['ir.cron'].sudo().create({
            'name': 'Arbitrary Cron',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'state': 'code',
            'code': 'model.search([])',
            'interval_type': 'days',
            'interval_number': 1,
        })

        # Attempt to rebind cron_id should fail
        with self.assertRaises(AccessError, msg="Should not allow cron_id rebinding"):
            self.alert_ny.write({'cron_id': arbitrary_cron.id})

        # Verify the original cron is still associated
        self.assertNotEqual(self.alert_ny.cron_id.id, arbitrary_cron.id)

    @common.users('cle-lunch-manager')
    def test_cron_ownership_verification_on_sync(self):
        """Test that _sync_cron verifies ownership before modifying cron."""
        # Store the original cron
        original_cron = self.alert_ny.cron_id

        # Create an arbitrary cron
        arbitrary_cron = self.env['ir.cron'].sudo().create({
            'name': 'Arbitrary Cron',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'state': 'code',
            'code': 'model.search([])',
            'interval_type': 'days',
            'interval_number': 1,
        })

        # Bypass write protection by using SQL to rebind cron_id
        self.env.cr.execute(
            "UPDATE lunch_alert SET cron_id = %s WHERE id = %s",
            (arbitrary_cron.id, self.alert_ny.id)
        )
        self.alert_ny.invalidate_recordset(['cron_id'])

        # Attempt to sync should fail due to ownership verification
        with self.assertRaises(AccessError, msg="Should detect cron ownership mismatch"):
            self.alert_ny._sync_cron()

    @common.users('cle-lunch-manager')
    def test_cron_ownership_verification_on_unlink(self):
        """Test that unlink verifies ownership before deleting cron."""
        # Create an arbitrary cron
        arbitrary_cron = self.env['ir.cron'].sudo().create({
            'name': 'Arbitrary Cron',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'state': 'code',
            'code': 'model.search([])',
            'interval_type': 'days',
            'interval_number': 1,
        })

        # Bypass write protection by using SQL to rebind cron_id
        self.env.cr.execute(
            "UPDATE lunch_alert SET cron_id = %s WHERE id = %s",
            (arbitrary_cron.id, self.alert_ny.id)
        )
        self.alert_ny.invalidate_recordset(['cron_id'])

        # Attempt to delete should fail due to ownership verification
        with self.assertRaises(AccessError, msg="Should detect cron ownership mismatch"):
            self.alert_ny.unlink()

        # Verify the arbitrary cron still exists
        self.assertTrue(arbitrary_cron.exists())


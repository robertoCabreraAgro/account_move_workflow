from odoo import models, fields


class AccountMoveWorkflowWizardLine(models.TransientModel):
    _name = 'account.move.workflow.wizard.line'
    _description = 'Workflow Wizard Line Preview'

    wizard_id = fields.Many2one('account.move.workflow.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer()
    template_id = fields.Many2one('account.move.template', string='Template')
    condition = fields.Char()
    will_execute = fields.Boolean(string='Will Execute')
    state = fields.Selection([
        ('valid', 'Valid'),
        ('error', 'Error'),
        ('pending', 'Pending')
    ], default='pending')
    error_message = fields.Text()

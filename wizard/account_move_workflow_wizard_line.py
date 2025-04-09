from odoo import api, fields, models, _

class AccountMoveWorkflowWizardLine(models.TransientModel):
    _name = 'account.move.workflow.wizard.line'
    _description = 'Workflow Wizard Line Preview'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('account.move.workflow.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer()
    template_id = fields.Many2one('account.move.template', string='Template')
    condition = fields.Char(readonly=True)
    will_execute = fields.Boolean(string='Will Execute')
    state = fields.Selection([
        ('valid', 'Valid'),
        ('error', 'Error'),
        ('pending', 'Pending')
    ], default='pending')
    error_message = fields.Text()
    template_line_id = fields.Many2one('account.move.workflow.template.line', string='Template Line')
    
    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Update state when template changes"""
        for line in self:
            if not line.template_id:
                line.state = 'error'
                line.error_message = 'No template selected'
            else:
                line.state = 'pending'
                line.error_message = False
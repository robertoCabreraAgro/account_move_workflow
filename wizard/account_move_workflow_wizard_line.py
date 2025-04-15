from odoo import api, fields, models, _

class AccountMoveWorkflowWizardLine(models.TransientModel):
    _name = 'account.move.workflow.wizard.line'
    _description = 'Workflow Wizard Line Preview'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        comodel_name='account.move.workflow.wizard', 
        required=True, 
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    template_id = fields.Many2one(
        comodel_name='account.move.template', 
        string='Template',
    )
    condition = fields.Char(readonly=True)
    will_execute = fields.Boolean(
        string='Will Execute',
        default=True
    )
    state = fields.Selection(
        selection=[
            ('valid', 'Valid'),
            ('error', 'Error'),
            ('pending', 'Pending')
        ], 
        default='pending',
    )
    error_message = fields.Text()
    workflow_template_ids = fields.Many2one(
        comodel_name='account.move.workflow.template', 
        string='Template Line',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='wizard_id.company_id',
        store=True,
    )
    
    @api.onchange('template_id')
    def _onchange_template_id(self):
        for line in self:
            if not line.template_id:
                line.state = 'error'
                line.error_message = _('No template selected')
            else:
                line.state = 'pending'
                line.error_message = False
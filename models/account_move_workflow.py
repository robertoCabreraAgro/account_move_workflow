from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountMoveWorkflow(models.Model):
    _name = 'account.move.workflow'
    _description = 'Accounting Workflow Template'
    _order = 'name'

    name = fields.Char(required=True, string='Workflow Name')
    code = fields.Char(string='Reference Code')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    partner_required = fields.Boolean(
        string='Partner Required',
        help='If checked, a partner will be required when executing this workflow'
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
        help='Default currency for this workflow'
    )
    amount_min = fields.Float(
        string='Minimum Amount',
        help='Minimum amount allowed for this workflow'
    )
    amount_max = fields.Float(
        string='Maximum Amount',
        help='Maximum amount allowed for this workflow (0 = no limit)'
    )
    note = fields.Text(string='Description')
    template_line_ids = fields.One2many(
        'account.workflow.template.line',
        'workflow_id',
        string='Template Lines'
    )
    generated_move_ids = fields.One2many(
        'account.move',
        'workflow_id',
        string='Generated Journal Entries'
    )
    generated_move_count = fields.Integer(
        string='Moves',
        compute='_compute_generated_move_count',
        store=True
    )

    @api.depends('generated_move_ids')
    def _compute_generated_move_count(self):
        for record in self:
            record.generated_move_count = len(record.generated_move_ids)
            
    @api.constrains('template_line_ids')
    def _check_template_sequences(self):
        for workflow in self:
            sequences = workflow.template_line_ids.mapped('sequence')
            if len(sequences) != len(set(sequences)):
                raise ValidationError(_('Template sequences must be unique within the same workflow'))
    
    
    def action_view_moves(self):
        """Abre la vista de los asientos contables generados por el workflow."""
        self.ensure_one()
        return {
            'name': _('Generated Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.generated_move_ids.ids)],
            'context': {'default_workflow_id': self.id},
        }
        
    def action_open_wizard(self):
        """Open the workflow execution wizard"""
        self.ensure_one()
        return {
            'name': _('Execute Workflow: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.workflow.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_workflow_id': self.id,
                'default_company_id': self.company_id.id,
                'default_currency_id': self.currency_id.id,
            }
        }


class AccountWorkflowTemplateLine(models.Model):
    _name = 'account.workflow.template.line'
    _description = 'Workflow Template Line'
    _order = 'sequence, id'

    workflow_id = fields.Many2one(
        'account.move.workflow',
        string='Workflow',
        required=True,
        ondelete='cascade'
    )
    template_id = fields.Many2one(
        'account.move.template',
        string='Move Template',
        required=True,
        domain="[('company_id', '=', parent.company_id)]"
    )
    sequence = fields.Integer(default=10)
    condition = fields.Char(
        string='Condition',
        help="Python condition to evaluate if this template should be applied. "
             "Available variables: partner, amount, currency, date, previous_moves"
    )
    skip_on_error = fields.Boolean(
        string='Skip on Error',
        help='If checked, workflow will continue even if this template fails'
    )
    
    @api.constrains('condition')
    def _check_condition_syntax(self):
        for line in self.filtered(lambda l: l.condition):
            try:
                compile(line.condition, '<string>', 'eval')
            except SyntaxError:
                raise ValidationError(_("Invalid Python syntax in condition: %s") % line.condition)
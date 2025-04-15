from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class AccountMoveWorkflowTemplateLine(models.Model):
    _name = 'account.move.workflow.template.line'
    _description = 'Workflow Template Line'
    _order = 'sequence, id'
    _check_company_auto = True

    workflow_id = fields.Many2one(
        comodel_name='account.move.workflow',
        string='Workflow',
        required=True,
        ondelete='cascade',
    )
    template_id = fields.Many2one(
        comodel_name='account.move.template',
        string='Move Template',
        required=True,
        domain="[('company_id', '=', parent.company_id)]",
    )
    sequence = fields.Integer(default=10)
    condition = fields.Char(
        string='Condition',
        help="Python condition to evaluate if this template should be applied. "
             "Available variables: partner, amount, currency, date, source_name, previous_moves"
    )
    skip_on_error = fields.Boolean(
        string='Skip on Error',
        default=False,
        help='If checked, workflow will continue even if this template fails'
    )
    overwrite = fields.Text(
        string='Overwrite Values',
        help="Python dictionary to overwrite template line values. Format: "
             "{'L1': {'amount': 100, 'name': 'Description'}, 'L2': {...}}"
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='workflow_id.company_id',
        store=True,
    )
    
    @api.constrains('condition')
    def _check_condition_syntax(self):
        for line in self.filtered(lambda l: l.condition):
            eval_context = {
                'partner': None, 
                'amount': 0.0, 
                'currency': None, 
                'date': None, 
                'source_name': '', 
                'previous_moves': [], 
                'env': self.env
            }
            try:
                safe_eval(line.condition, eval_context)
            except (SyntaxError, ValueError) as e:
                raise ValidationError(_("Invalid Python syntax in condition: %s\nError: %s") % (line.condition, str(e)))
                
    @api.constrains('overwrite')
    def _check_overwrite_syntax(self):
        for line in self.filtered(lambda l: l.overwrite):
            eval_context = {
                'partner': None, 
                'amount': 0.0, 
                'currency': None, 
                'date': None, 
                'source_name': '', 
                'previous_moves': [], 
                'env': self.env
            }
            try:
                safe_eval(line.overwrite, eval_context)
            except (SyntaxError, ValueError) as e:
                raise ValidationError(_("Invalid Python syntax in overwrite values: %s\nError: %s") % (line.overwrite, str(e)))
    
    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id and self.template_id.company_id != self.workflow_id.company_id:
            self.template_id = False
            return {
                'warning': {
                    'title': _('Wrong Company'),
                    'message': _('Template must belong to the same company as the workflow.')
                }
            }
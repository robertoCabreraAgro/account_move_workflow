# models/account_move_template_line.py
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountMoveWorkflowTemplateLine(models.Model):
    _name = 'account.move.workflow.template.line'
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
    overwrite = fields.Text(
        string='Overwrite Values',
        help="Python dictionary to overwrite template line values. Format: "
             "{'L1': {'amount': 100, 'name': 'Description'}, 'L2': {...}}"
    )
    
    @api.constrains('condition')
    def _check_condition_syntax(self):
        for line in self.filtered(lambda l: l.condition):
            try:
                safe_eval(line.condition, {'partner': None, 'amount': 0, 'currency': None, 'date': None, 'previous_moves': [], 'env': self.env})
            except (SyntaxError, ValueError) as e:
                raise ValidationError(_("Invalid Python syntax in condition: %s\nError: %s") % (line.condition, str(e)))
                
    @api.constrains('overwrite')
    def _check_overwrite_syntax(self):
        for line in self.filtered(lambda l: l.overwrite):
            try:
                safe_eval(line.overwrite, {'partner': None, 'amount': 0, 'currency': None, 'date': None, 'previous_moves': [], 'env': self.env})
            except (SyntaxError, ValueError) as e:
                raise ValidationError(_("Invalid Python syntax in overwrite values: %s\nError: %s") % (line.overwrite, str(e)))
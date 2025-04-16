from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class AccountMoveWorkflowTemplate(models.Model):
    _name = 'account.move.workflow.template'
    _description = 'Workflow Template'
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
        domain="[('company_id', '=', company_id)]",
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
    target_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Target Company',
        help="If set, this company will be used to create the journal entry, "
             "regardless of the workflow or template company",
    )
    use_template_company = fields.Boolean(
        string='Use Template Company',
        default=True,
        help="If checked, the company specified in the template will be used"
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
        if self.template_id:
            if self.template_id.company_id != self.workflow_id.company_id and not self.target_company_id:
                # Si el template es de otra compañía, sugerir usar esa como target_company_id
                self.target_company_id = self.template_id.company_id
                self.use_template_company = True
            
            # Si el template tiene target_company_id, sugerimos usar esa
            if hasattr(self.template_id, 'target_company_id') and self.template_id.target_company_id:
                self.target_company_id = self.template_id.target_company_id
                self.use_template_company = True
                
    @api.onchange('use_template_company')
    def _onchange_use_template_company(self):
        for record in self:
            if record.use_template_company and record.template_id:
                # Usar la target_company_id del template si existe
                if hasattr(record.template_id, 'target_company_id') and record.template_id.target_company_id:
                    record.target_company_id = record.template_id.target_company_id
                else:
                    record.target_company_id = record.template_id.company_id
            elif not record.use_template_company:
                record.target_company_id = False
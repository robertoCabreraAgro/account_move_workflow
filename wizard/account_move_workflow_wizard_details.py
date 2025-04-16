from odoo import api, fields, models, _

class AccountMoveWorkflowWizardDetails(models.TransientModel):
    _name = 'account.move.workflow.wizard.details'
    _description = 'Workflow Wizard Details Preview'
    _order = 'wizard_line_id, sequence, id'

    wizard_id = fields.Many2one(
        comodel_name='account.move.workflow.wizard', 
        required=True, 
        ondelete='cascade',
    )
    wizard_line_id = fields.Many2one(
        comodel_name='account.move.workflow.wizard.line', 
        string='Wizard Line',
    )
    template_id = fields.Many2one(
        comodel_name='account.move.template', 
        related="wizard_line_id.template_id",
        string='Template',
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='wizard_id.company_id',
        store=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)
    name = fields.Char(string="Label")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
        domain="['|', ('parent_id', '=', False), ('is_company', '=', True)]",
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Account",
        required=True,
        check_company=True,
        domain="[('deprecated', '=', False), ('account_type', '!=', 'off_balance')]",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        check_company=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit of Measure",
        compute="_compute_product_uom_id",
        store=True,
        readonly=False,
    )
    quantity = fields.Float(
        string="Quantity",
        digits="Product Unit of Measure",
        default=1.0,
    )
    amount = fields.Float(default=0.0)
    tax_ids = fields.Many2many(
        comodel_name="account.tax",
        string="Taxes",
        check_company=True,
    )
    move_line_type = fields.Selection(
        selection=[("cr", "Credit"), ("dr", "Debit")],
        string="Direction",
        required=True,
    )
    template_line_type = fields.Selection(
        selection=[
            ("input", "User input"),
            ("computed", "Computed"),
        ],
        string="Line Type",
        readonly=True,
    )
    template_line_id = fields.Many2one(
        comodel_name="account.move.template.line",
        string="Template Line",
        readonly=True,
    )
    template_python_code = fields.Text(
        string="Formula",
        readonly=True,
    )
    
    @api.depends('product_id')
    def _compute_product_uom_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
            else:
                line.product_uom_id = False
    
    @api.onchange('wizard_line_id')
    def _onchange_wizard_line_id(self):
        for line in self:
            if not line.wizard_line_id or not line.wizard_line_id.template_id:
                continue
                
            line.template_id = line.wizard_line_id.template_id.id
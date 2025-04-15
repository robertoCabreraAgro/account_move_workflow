from odoo import api, fields, models, _

class AccountMoveWorkflowWizardDetails(models.TransientModel):
    _name = 'account.move.workflow.wizard.details'
    _description = 'Workflow Wizard Details Preview'
    _order = 'id'

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
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='wizard_id.company_id',
        store=True,
    )
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
    
    @api.onchange('template_id')
    def _onchange_template_id(self):
        for line in self:
            if not line.template_id:
                line.state = 'error'
                line.error_message = _('No template selected')
            else:
                line.state = 'pending'
                line.error_message = False
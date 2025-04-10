from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class AccountMoveWorkflowWizard(models.TransientModel):
    _name = 'account.move.workflow.wizard'
    _description = 'Execute Accounting Workflow'

    workflow_id = fields.Many2one(
        'account.move.workflow',
        string='Workflow',
        required=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner'
    )
    amount = fields.Monetary(
        string='Amount'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    date = fields.Date(
        string='Accounting Date',
        required=True,
        default=fields.Date.context_today
    )
    source_move_id = fields.Many2one(
        'account.move',
        string='Source Move',
        help='Journal entry that triggered this workflow'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('preview', 'Preview')
    ], default='draft')
    
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('company_id', '=', company_id)]"
    )
    template_preview_ids = fields.One2many(
        'account.move.workflow.wizard.line',
        'wizard_id',
        string='Template Preview'
    )

    reference = fields.Char(string="Reference")
    require_partner = fields.Boolean(compute='_compute_requirements')
    require_amount = fields.Boolean(compute='_compute_requirements')

    @api.depends('workflow_id')
    def _compute_requirements(self):
        for wizard in self:
            wizard.require_partner = wizard.workflow_id.partner_required if wizard.workflow_id else False
            wizard.require_amount = True
    
    @api.onchange('workflow_id')
    def _onchange_workflow(self):
        if self.workflow_id:
            self.currency_id = self.workflow_id.currency_id
            
            # Update template previews
            template_lines = self.workflow_id.template_line_ids.sorted(lambda l: l.sequence)
            preview_vals = []
            
            for line in template_lines:
                preview_vals.append({
                    'sequence': line.sequence,
                    'template_id': line.template_id.id,
                    'template_line_id': line.id,
                    'condition': line.condition,
                    'will_execute': True,
                    'state': 'pending'
                })
            
            # Delete existing lines and create new ones
            self.template_preview_ids = [(5, 0, 0)]
            for val in preview_vals:
                self.template_preview_ids = [(0, 0, val)]
                
            if self.workflow_id.partner_required and not self.partner_id:
                return {'warning': {
                    'title': _('Partner Required'),
                    'message': _('This workflow requires selecting a partner.')
                }}
    
    @api.onchange('partner_id', 'amount', 'currency_id', 'date')
    def _onchange_parameters(self):
        """Update template preview when parameters change"""
        if not self.workflow_id or not self.template_preview_ids:
            return
            
        eval_context = self._get_eval_context()
        
        for line in self.template_preview_ids:
            if not line.condition:
                line.will_execute = True
                line.state = 'valid'
                continue
                
            try:
                result = self._safe_eval(line.condition, eval_context)
                line.will_execute = bool(result)
                line.state = 'valid'
                line.error_message = False
            except Exception as e:
                line.will_execute = False
                line.state = 'error'
                line.error_message = str(e)
    
    def _get_eval_context(self):
        """Return the evaluation context for conditions"""
        return {
            'partner': self.partner_id,
            'amount': self.amount,
            'currency': self.currency_id,
            'date': self.date,
            'env': self.env,
            'user': self.env.user,
            'company': self.company_id,
        }
    
    def action_preview(self):
        """Preview the workflow execution without creating actual moves"""
        self.ensure_one()
        
        # Validate required fields
        self._validate_workflow_requirements()
        
        # Update template states
        self._onchange_parameters()
        
        # Set preview state
        self.write({'state': 'preview'})
        
        return {
            'name': _('Preview Workflow Execution'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.workflow.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_execute(self):
        """Execute the workflow and create journal entries"""
        self.ensure_one()
        
        # Validate required fields
        self._validate_workflow_requirements()
        
        # Process templates in sequence order
        templates = self.workflow_id.template_line_ids.sorted(lambda l: l.sequence)
        created_moves = self.env['account.move']
        
        # Base context for conditions
        eval_context = self._get_eval_context()
        eval_context['previous_moves'] = []
        
        # Create a workflow reference
        workflow_ref = f"WORKFLOW/{self.workflow_id.code or self.workflow_id.name[:5]}/{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        sequence = 1
        for line in templates:
            try:
                # Check condition if exists
                if line.condition and not self._safe_eval(line.condition, eval_context):
                    _logger.info(f"Skipping template {line.template_id.name}: condition not met")
                    continue
                
                # Prepare context for executing the template
                template = line.template_id
                
                # Use the account_move_template_run module to generate the entry
                wizard_vals = {
                    'template_id': template.id,
                    'date': self.date,
                    'journal_id': template.journal_id.id if template.journal_id else self.journal_id.id,
                    'partner_id': self.partner_id.id if self.partner_id else False,
                    'ref': f"{workflow_ref}/{sequence}",
                }
                
                # If overwrite is defined, add it
                if line.overwrite:
                    overwrite_dict = safe_eval(line.overwrite, eval_context)
                    wizard_vals['overwrite'] = str(overwrite_dict)
                
                # Create and execute the wizard for this template
                template_run = self.env['account.move.template.run'].create(wizard_vals)
                template_run.load_lines()
                
                # Set amounts according to configuration
                # In a complete implementation, this should follow configurable logic
                if self.amount and template_run.line_ids:
                    # Assign amount to the first line of type input
                    input_lines = template_run.line_ids.filtered(lambda l: l.move_line_type == 'dr')
                    if input_lines:
                        input_lines[0].amount = self.amount
                
                # Generate the entry
                result = template_run.generate_move()
                if result and result.get('res_id'):
                    move = self.env['account.move'].browse(result['res_id'])
                    
                    # Update entry data
                    move.write({
                        'workflow_id': self.workflow_id.id,
                        'workflow_sequence': sequence,
                    })
                    
                    created_moves += move
                    
                    # Update context for next template
                    eval_context['previous_moves'] = created_moves
                    
                sequence += 1
                
            except Exception as e:
                _logger.error(f"Error executing workflow template {line.template_id.name}: {str(e)}")
                if not line.skip_on_error:
                    # If errors should not be skipped, reverse everything
                    created_moves.button_draft()
                    created_moves.unlink()
                    raise UserError(_(
                        "Error executing template %(template)s (sequence %(sequence)d): %(error)s"
                    ) % {
                        'template': line.template_id.name,
                        'sequence': line.sequence,
                        'error': str(e)
                    })
        
        # Create relations between entries
        if len(created_moves) > 1:
            for move in created_moves:
                related_moves = created_moves - move
                if related_moves:
                    move.write({'related_move_ids': [(6, 0, related_moves.ids)]})
        
        # Display created entries
        if not created_moves:
            raise UserError(_("No journal entries were created. Please check template conditions."))
            
        action = {
            'name': _('Generated Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_moves.ids)],
            'context': {'create': False}
        }
        
        if len(created_moves) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': created_moves.id,
            })
            
        return action
    
    def _validate_workflow_requirements(self):
        """Validate all workflow requirements before execution"""
        self.ensure_one()
        
        errors = []
        workflow = self.workflow_id
        
        # Check partner if required
        if workflow.partner_required and not self.partner_id:
            errors.append(_("Partner is required for this workflow."))
        
        # Check amount limits
        if workflow.amount_min > 0 and self.amount < workflow.amount_min:
            errors.append(_(
                "Amount (%(amount)s) is below minimum allowed (%(min)s)."
            ) % {'amount': self.amount, 'min': workflow.amount_min})
        
        if workflow.amount_max > 0 and self.amount > workflow.amount_max:
            errors.append(_(
                "Amount (%(amount)s) is above maximum allowed (%(max)s)."
            ) % {'amount': self.amount, 'max': workflow.amount_max})
            
        # Check if partner has proper accounts for the currency
        if self.partner_id:
            # Check that the partner has configured accounts
            if not self.partner_id.property_account_receivable_id:
                errors.append(_("Partner %s doesn't have a receivable account configured.") % self.partner_id.name)
            if not self.partner_id.property_account_payable_id:
                errors.append(_("Partner %s doesn't have a payable account configured.") % self.partner_id.name)
        
        # Check templates existence
        if not workflow.template_line_ids:
            errors.append(_("This workflow doesn't have any templates configured."))
        
        if errors:
            raise ValidationError("\n".join(errors))
        
        return True
    
    def _safe_eval(self, expr, eval_context):
        """Safely evaluate a python expression with given context"""
        try:
            return safe_eval(expr, locals_dict=eval_context, nocopy=True)
        except Exception as e:
            raise UserError(_(
                "Error evaluating condition: %(condition)s\nError: %(error)s"
            ) % {'condition': expr, 'error': str(e)})
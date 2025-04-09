from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
import json
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
        string='Amount',
        required=True
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
    preview_data = fields.Text(
        string='Preview Data',
        readonly=True
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
    require_partner = fields.Boolean(compute='_compute_requirements', store=False)
    require_amount = fields.Boolean(compute='_compute_requirements', store=False)

    @api.depends('workflow_id')
    def _compute_requirements(self):
        for wizard in self:
            wizard.require_partner = wizard.workflow_id.partner_required
            wizard.require_amount = True  # O lo que decida tu lógica
    
    @api.onchange('workflow_id')
    def _onchange_workflow(self):
        if self.workflow_id:
            self.currency_id = self.workflow_id.currency_id
            if self.workflow_id.partner_required and not self.partner_id:
                return {'warning': {
                    'title': _('Partner Required'),
                    'message': _('This workflow requires selecting a partner.')
                }}
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            # Check if partner has accounts configured
            if self.workflow_id.partner_required:
                if not self.partner_id.property_account_receivable_id or not self.partner_id.property_account_payable_id:
                    return {'warning': {
                        'title': _('Missing Partner Accounts'),
                        'message': _('The selected partner does not have all required accounts configured.')
                    }}
    
    def action_preview(self):
        """Preview the workflow execution without creating actual moves"""
        self.ensure_one()
        
        # Validate required fields
        self._validate_workflow_requirements()
        
        # Initialize context for templates execution
        preview_data = []
        
        # Process templates in sequence order
        templates = self.workflow_id.template_line_ids.sorted(lambda l: l.sequence)
        
        # Base context for conditions
        eval_context = {
            'partner': self.partner_id,
            'amount': self.amount,
            'currency': self.currency_id,
            'date': self.date,
            'previous_moves': [],
            'env': self.env,
        }
        
        for line in templates:
            try:
                # Check condition if exists
                if line.condition:
                    condition_result = self._safe_eval(line.condition, eval_context)
                    if not condition_result:
                        preview_data.append({
                            'sequence': line.sequence,
                            'template': line.template_id.name,
                            'status': 'skipped',
                            'message': _('Condition not met')
                        })
                        continue
                
                # Simulate execution of template
                template = line.template_id
                # Here we would normally call template generation code
                # But for preview we just show what would be generated
                
                preview_data.append({
                    'sequence': line.sequence,
                    'template': template.name,
                    'status': 'ok',
                    'message': _('Will create entry based on template'),
                    'accounts': [{'code': line.account_id.code, 'name': line.account_id.name} 
                                 for line in template.line_ids]
                })
                
            except Exception as e:
                preview_data.append({
                    'sequence': line.sequence,
                    'template': line.template_id.name,
                    'status': 'error',
                    'message': str(e)
                })
                if not line.skip_on_error:
                    break
        
        self.write({
            'preview_data': json.dumps(preview_data),
            'state': 'preview'
        })
        
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
        eval_context = {
            'partner': self.partner_id,
            'amount': self.amount,
            'currency': self.currency_id,
            'date': self.date,
            'previous_moves': [],
            'env': self.env,
        }
        
        # Create a workflow reference
        workflow_ref = f"WORKFLOW/{self.workflow_id.code or self.workflow_id.name}/{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        sequence = 1
        for line in templates:
            try:
                # Check condition if exists
                if line.condition and not self._safe_eval(line.condition, eval_context):
                    continue
                
                # Execute the template
                template = line.template_id
                
                # Prepare context for template execution
                template_ctx = {
                    'default_template_id': template.id,
                    'default_partner_id': self.partner_id.id if self.partner_id else False,
                    'default_date': self.date,
                    'default_workflow_id': self.workflow_id.id,
                    'default_workflow_sequence': sequence,
                    'default_ref': workflow_ref,
                    'default_previous_moves': created_moves,
                }
                
                # Generate moves from template
                # We'll need to extend account_move_template to support our parameters
                # For now, we'll just create a simple move for demonstration
                move_vals = {
                    'date': self.date,
                    'ref': workflow_ref,
                    'journal_id': template.journal_id.id,
                    'company_id': self.company_id.id,
                    'workflow_id': self.workflow_id.id,
                    'workflow_sequence': sequence,
                    'partner_id': self.partner_id.id if self.partner_id else False,
                    # We would add move lines here based on template configuration
                }
                
                new_move = self.env['account.move'].create(move_vals)
                created_moves += new_move
                
                # Update eval context with new move
                eval_context['previous_moves'] = created_moves
                
                sequence += 1
                
            except Exception as e:
                _logger.error(f"Error executing workflow template {line.template_id.name}: {str(e)}")
                if not line.skip_on_error:
                    # Clean up - delete created moves if one fails and we're not skipping errors
                    created_moves.unlink()
                    raise UserError(_(
                        "Error executing template %(template)s (sequence %(sequence)d): %(error)s"
                    ) % {
                        'template': line.template_id.name,
                        'sequence': line.sequence,
                        'error': str(e)
                    })
        
        # Create relations between moves
        if len(created_moves) > 1:
            for move in created_moves:
                related_moves = created_moves - move
                move.write({'related_move_ids': [(6, 0, related_moves.ids)]})
        
        # Show the created moves
        action = {
            'name': _('Generated Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_moves.ids)],
        }
        
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
            # This is simplified, in a real implementation we would check
            # specific accounts based on the templates used
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
            return eval(expr, {'__builtins__': {}}, eval_context)
        except Exception as e:
            raise UserError(_(
                "Error evaluating condition: %(condition)s\nError: %(error)s"
            ) % {'condition': expr, 'error': str(e)})
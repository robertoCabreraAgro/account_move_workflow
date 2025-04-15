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
        comodel_name='account.move.workflow',
        string='Workflow',
        required=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
    )
    amount = fields.Monetary(
        string='Amount',
        default=0.0
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
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
        comodel_name='account.move',
        string='Source Move',
        help='Journal entry that triggered this workflow',

    )
    source_move_name = fields.Char(
        string='Source Entry Name',
        help='Name/Number of the journal entry that triggered this workflow'
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('preview', 'Preview')
        ],
        default='draft'
    )
    
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        domain="[('company_id', '=', company_id)]",

    )
    template_preview_ids = fields.One2many(
        comodel_name='account.move.workflow.wizard.line',
        inverse_name='wizard_id',
        string='Template Preview'
    )

    reference = fields.Char(string="Reference")
    require_partner = fields.Boolean(compute='_compute_requirements')
    require_amount = fields.Boolean(compute='_compute_requirements')
    price_unit = fields.Float(
        string='Unit Price',
        help='Price per unit to be transferred to the generated move lines',
        default=0.0
    )

    @api.depends('workflow_id')
    def _compute_requirements(self):
        for wizard in self:
            wizard.require_partner = wizard.workflow_id.partner_required if wizard.workflow_id else False
            wizard.require_amount = True
    
    @api.onchange('workflow_id')
    def _onchange_workflow(self):
        if self.workflow_id:
            self.currency_id = self.workflow_id.currency_id
            
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
            
            self.template_preview_ids = [(5, 0, 0)]
            for val in preview_vals:
                self.template_preview_ids = [(0, 0, val)]
                
            if self.workflow_id.partner_required and not self.partner_id:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Partner Required'),
                        'message': _('This workflow requires selecting a partner.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
                
            if self.amount:
                self.price_unit = self.amount
    
    @api.onchange('amount')
    def _onchange_amount(self):
        if self.amount:
            self.price_unit = self.amount
    
    @api.onchange('partner_id', 'amount', 'currency_id', 'date')
    def _onchange_parameters(self):
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
        return {
            'partner': self.partner_id,
            'amount': self.amount,
            'currency': self.currency_id,
            'date': self.date,
            'env': self.env,
            'user': self.env.user,
            'company': self.company_id,
            'source_name': self.source_move_name or '',
        }
    
    def action_execute(self):
        self.ensure_one()
        
        self._validate_workflow_requirements()
        
        templates = self.workflow_id.template_line_ids.sorted(lambda l: l.sequence)
        created_moves = self.env['account.move']
        
        eval_context = self._get_eval_context()
        eval_context['previous_moves'] = []
        
        workflow_ref = f"WORKFLOW/{self.workflow_id.code or self.workflow_id.name[:5]}/{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if self.source_move_name:
            workflow_ref = f"{workflow_ref}/{self.source_move_name}"
        
        sequence = 1
        for line in templates:
            try:
                if line.condition and not self._safe_eval(line.condition, eval_context):
                    _logger.info(f"Skipping template {line.template_id.name}: condition not met")
                    continue
                
                template = line.template_id
                
                template_run_vals = {
                    'template_id': template.id,
                    'date': self.date,
                    'journal_id': template.journal_id.id if template.journal_id else self.journal_id.id,
                    'partner_id': self.partner_id.id if self.partner_id else template.partner_id.id if template.partner_id else False,
                    'ref': self.reference,
                    'move_type': template.move_type,
                    'price_unit': self.price_unit or self.amount,
                }
                
                if hasattr(template, 'date') and template.date:
                    template_run_vals['date'] = template.date
                
                if line.overwrite:
                    overwrite_dict = safe_eval(line.overwrite, eval_context)
                    template_run_vals['overwrite'] = str(overwrite_dict)
                
                template_run = self.env['account.move.template.run'].create(template_run_vals)
                _logger.info("template_run %s, %s", template_run, template_run.read())
                
                result = template_run.load_lines()
                
                if hasattr(template_run, 'line_ids') and template_run.line_ids:
                    input_lines = template_run.line_ids.filtered(lambda l: hasattr(l, 'template_type') and l.template_type == 'input')
                    if input_lines:
                        input_lines[0].amount = self.amount
                        
                    for line in template_run.line_ids:
                        if hasattr(line, 'price_unit'):
                            line.price_unit = self.price_unit or self.amount
                
                move_result = template_run.with_context(**result.get('context', {})).generate_move()
                
                if move_result and move_result.get('res_id'):
                    move = self.env['account.move'].browse(move_result['res_id'])
                    
                    move.write({
                        'workflow_id': self.workflow_id.id,
                        'workflow_sequence': sequence,
                    })
                    
                    if self.price_unit or self.amount:
                        for move_line in move.line_ids:
                            move_line.price_unit = self.price_unit or self.amount
                    
                    created_moves += move
                    eval_context['previous_moves'] = created_moves
                    
                sequence += 1
                
            except Exception as e:
                _logger.error(f"Error executing workflow template {line.template_id.name}: {str(e)}")
                if not line.skip_on_error:
                    created_moves.button_draft()
                    created_moves.unlink()
                    raise UserError(_(
                        "Error executing template %(template)s (sequence %(sequence)d): %(error)s"
                    ) % {
                        'template': line.template_id.name,
                        'sequence': line.sequence,
                        'error': str(e)
                    })
        
        if len(created_moves) > 1:
            for move in created_moves:
                related_moves = created_moves - move
                if related_moves:
                    move.write({'related_move_ids': [(6, 0, related_moves.ids)]})
        
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
        self.ensure_one()
        
        errors = []
        workflow = self.workflow_id
        
        if workflow.partner_required and not self.partner_id:
            errors.append(_("Partner is required for this workflow."))
            
        if not workflow.template_line_ids:
            errors.append(_("This workflow doesn't have any templates configured."))
        
        if errors:
            raise ValidationError("\n".join(errors))
        
        return True
    
    def _safe_eval(self, expr, eval_context):
        try:
            return safe_eval(expr, locals_dict=eval_context, nocopy=True)
        except Exception as e:
            raise UserError(_(
                "Error evaluating condition: %(condition)s\nError: %(error)s"
            ) % {'condition': expr, 'error': str(e)})
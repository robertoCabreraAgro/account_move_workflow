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
    source_move_name = fields.Char(
        string='Source Entry Name',
        help='Name/Number of the journal entry that triggered this workflow'
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
    
    # Añadimos el campo price_unit para transferirlo a las líneas del asiento
    price_unit = fields.Float(
        string='Unit Price',
        help='Price per unit to be transferred to the generated move lines'
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
                
            # Si hay un amount, transferirlo al price_unit
            if self.amount:
                self.price_unit = self.amount
    
    @api.onchange('amount')
    def _onchange_amount(self):
        """Transferir amount a price_unit cuando cambia"""
        if self.amount:
            self.price_unit = self.amount
    
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
            'source_name': self.source_move_name,
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
        """Execute the workflow and create journal entries via templates"""
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
        if self.source_move_name:
            workflow_ref = f"{workflow_ref}/{self.source_move_name}"
        
        sequence = 1
        for line in templates:
            try:
                # Check condition if exists
                if line.condition and not self._safe_eval(line.condition, eval_context):
                    _logger.info(f"Skipping template {line.template_id.name}: condition not met")
                    continue
                
                # Get the template
                template = line.template_id
                
                # Use the account_move_template_run module to generate the entry
                wizard_vals = {
                    'template_id': template.id,
                    'date': self.date,
                    'journal_id': template.journal_id.id if template.journal_id else self.journal_id.id,
                    'partner_id': self.partner_id.id if self.partner_id else template.partner_id.id if template.partner_id else False,
                    'ref': f"{workflow_ref}/{sequence}" if self.reference else f"{self.source_move_name or ''} - {template.name}",
                    'move_type': template.move_type,
                    'price_unit': self.price_unit or self.amount,  # Asegurar que price_unit siempre tenga un valor
                }
                
                # Si el template tiene fecha propia, usarla en lugar de la fecha del wizard
                if hasattr(template, 'date') and template.date:
                    wizard_vals['date'] = template.date
                
                # Si overwrite está definido, añadirlo
                if line.overwrite:
                    overwrite_dict = safe_eval(line.overwrite, eval_context)
                    wizard_vals['overwrite'] = str(overwrite_dict)
                
                # Crear y ejecutar el wizard para este template
                template_run = self.env['account.move.template.run'].create(wizard_vals)
                
                # El método load_lines carga las líneas del template
                result = template_run.load_lines()
                
                # Si se necesita sobrescribir los valores después de cargar líneas
                if hasattr(template_run, 'line_ids') and template_run.line_ids:
                    # Asignar montos según configuración
                    # Solo sobrescribimos si hay líneas de tipo input
                    input_lines = template_run.line_ids.filtered(lambda l: hasattr(l, 'template_type') and l.template_type == 'input')
                    if input_lines:
                        # Asignar el monto a la primera línea de tipo input
                        input_lines[0].amount = self.amount
                        
                    # También asignar el price_unit a todas las líneas del wizard
                    for line in template_run.line_ids:
                        if hasattr(line, 'price_unit'):
                            line.price_unit = self.price_unit or self.amount
                
                # Generar el asiento usando el propio método del template
                move_result = template_run.with_context(**result.get('context', {})).generate_move()
                
                if move_result and move_result.get('res_id'):
                    move = self.env['account.move'].browse(move_result['res_id'])
                    
                    # Actualizar datos del asiento
                    move.write({
                        'workflow_id': self.workflow_id.id,
                        'workflow_sequence': sequence,
                    })
                    
                    # Actualizar el price_unit en todas las líneas del asiento creado
                    if self.price_unit or self.amount:
                        for move_line in move.line_ids:
                            move_line.price_unit = self.price_unit or self.amount
                    
                    created_moves += move
                    
                    # Actualizar el contexto para el siguiente template
                    eval_context['previous_moves'] = created_moves
                    
                sequence += 1
                
            except Exception as e:
                _logger.error(f"Error executing workflow template {line.template_id.name}: {str(e)}")
                if not line.skip_on_error:
                    # Si no se deben ignorar errores, revertir todo
                    created_moves.button_draft()
                    created_moves.unlink()
                    raise UserError(_(
                        "Error executing template %(template)s (sequence %(sequence)d): %(error)s"
                    ) % {
                        'template': line.template_id.name,
                        'sequence': line.sequence,
                        'error': str(e)
                    })
        
        # Crear relaciones entre asientos
        if len(created_moves) > 1:
            for move in created_moves:
                related_moves = created_moves - move
                if related_moves:
                    move.write({'related_move_ids': [(6, 0, related_moves.ids)]})
        
        # Mostrar asientos creados
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
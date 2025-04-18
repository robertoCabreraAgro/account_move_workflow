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
    line_ids= fields.One2many(
        comodel_name='account.move.workflow.wizard.line',
        inverse_name='wizard_id',
        string='Template'
    )
    details_ids = fields.One2many(
        comodel_name='account.move.workflow.wizard.details',
        inverse_name='wizard_id',
        string='Template Details'
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
            
            # Limpiar líneas existentes
            self.line_ids = [(5, 0, 0)]
            self.details_ids = [(5, 0, 0)]
            
            template_lines = self.workflow_id.workflow_template_ids.sorted(lambda l: l.sequence)
            wizard_line_vals = []
            
            for line in template_lines:
                wizard_line_vals.append({
                    'sequence': line.sequence,
                    'template_id': line.template_id.id,
                    'workflow_template_ids': line.id,
                    'condition': line.condition,
                    'will_execute': True,
                    'state': 'pending'
                })
            
            for val in wizard_line_vals:
                self.line_ids = [(0, 0, val)]
            
            # Cargar detalles para cada template
            self._load_template_details()
                
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
    
    def _load_template_details(self):
        """Carga todas las líneas de todos los templates asociados al workflow"""
        if not self.workflow_id or not self.line_ids:
            return
            
        templates = self.line_ids.mapped('template_id')
        detail_vals = []
        seq = 1
        
        for wiz_line in self.line_ids:
            template = wiz_line.template_id
            if not template:
                continue
                
            template_lines = self.env['account.move.template.line'].search(
                [('template_id', '=', template.id)], order='sequence'
            )
            
            for tmpl_line in template_lines:
                detail_vals.append({
                    'wizard_id': self.id,
                    'wizard_line_id': wiz_line.id,
                    'name': tmpl_line.name,
                    'sequence': seq,
                    'account_id': tmpl_line.account_id.id,
                    'partner_id': tmpl_line.partner_id.id if tmpl_line.partner_id else False,
                    'move_line_type': tmpl_line.move_line_type,
                    'tax_ids': [(6, 0, tmpl_line.tax_ids.ids)] if hasattr(tmpl_line, 'tax_ids') else False,
                    'product_id': tmpl_line.product_id.id if hasattr(tmpl_line, 'product_id') and tmpl_line.product_id else False,
                    'quantity': tmpl_line.quantity if hasattr(tmpl_line, 'quantity') else 1.0,
                    'amount': 0.0,  # Será calculado luego
                    'template_line_type': tmpl_line.type if hasattr(tmpl_line, 'type') else 'input',
                    'template_line_id': tmpl_line.id,
                    'template_python_code': tmpl_line.python_code if hasattr(tmpl_line, 'python_code') else False,
                })
                seq += 1
                
        for val in detail_vals:
            self.details_ids = [(0, 0, val)]
    
    @api.onchange('amount')
    def _onchange_amount(self):
        if self.amount:
            self.price_unit = self.amount
            
            # Actualizar cantidades en detalles
            if self.details_ids:
                # Aplicar la lógica para asignar montos a las líneas 
                # basado en los tipos de línea (computed/input) del template original
                self._update_details_amounts()
    
    def _update_details_amounts(self):
        """Actualiza los montos en las líneas de detalles según la lógica del template"""
        if not self.details_ids:
            return
            
        # Obtener la lógica de los templates originales para cálculos
        for wiz_line in self.line_ids:
            template = wiz_line.template_id
            if not template:
                continue
                
            details = self.details_ids.filtered(lambda d: d.wizard_line_id.id == wiz_line.id)
            if not details:
                continue
                
            # Buscar líneas de entrada (input) y asignar valor proporcional
            input_details = details.filtered(lambda d: d.template_line_type == 'input')
            if input_details and self.amount:
                # Para simplificar, asignaremos el monto total a la primera línea de débito
                input_details[0].amount = self.amount
                
                # El resto podría calcularse según la lógica del template original
                # Aquí podríamos replicar la lógica de cálculo del template, pero
                # por simplicidad dejamos las otras líneas en 0 por ahora
    
    @api.onchange('partner_id', 'amount', 'currency_id', 'date')
    def _onchange_parameters(self):
        if not self.workflow_id or not self.line_ids:
            return
            
        eval_context = self._get_eval_context()
        
        for line in self.line_ids:
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
                
        # Actualizar detalles si es necesario
        if self.amount:
            self._update_details_amounts()
    
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
        
        templates = self.workflow_id.workflow_template_ids.sorted(lambda l: l.sequence)
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
                
                # Usar la compañía destino definida en el template si existe
                target_company_id = template.target_company_id.id if hasattr(template, 'target_company_id') and template.target_company_id else self.company_id.id
                
                template_run_vals = {
                    'template_id': template.id,
                    'date': self.date,
                    'journal_id': template.journal_id.id if template.journal_id else self.journal_id.id,
                    'partner_id': self.partner_id.id if self.partner_id else template.partner_id.id if template.partner_id else False,
                    'ref': self.reference,
                    'move_type': template.move_type,
                    'price_unit': self.price_unit or self.amount,
                    'company_id': target_company_id,  # Usar la compañía destino
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
                    created_moves.with_context(force_delete=True).button_draft()
                    created_moves.with_context(force_delete=True).unlink()
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
            
        if not workflow.workflow_template_ids:
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
from odoo import api, fields, models, _
from itertools import chain
from odoo.tools.safe_eval import safe_eval

import logging


_logger = logging.getLogger(__name__)

class AccountMoveWorkflowTemplate(models.Model):
    _inherit = 'account.move.template'
    
    workflow_line_ids = fields.One2many(
        'account.move.workflow.template.line',
        'template_id',
        string='Used in Workflows'
    )
    workflow_count = fields.Integer(
        string='# Workflows',
        compute='_compute_workflow_count'
    )

    def _compute_workflow_count(self):
        """Compute the number of workflows this template is used in"""
        for template in self:
            template.workflow_count = len(template.workflow_line_ids)
    
    def action_view_workflows(self):
        """View workflows where this template is used"""
        self.ensure_one()
        workflows = self.workflow_line_ids.mapped('workflow_id')
        
        if not workflows:
            return {
                'type': 'ir.actions.act_window_close'
            }
            
        action = self.env.ref('account_move_workflow.action_account_move_workflow').read()[0]
        
        workflow_ids = workflows.ids
        if len(workflow_ids) == 1:
            action['views'] = [(self.env.ref('account_move_workflow.view_account_move_workflow_form').id, 'form')]
            action['res_id'] = workflow_ids[0]
        else: 
            action['domain'] = [('id', 'in', workflow_ids)]
            
        return action
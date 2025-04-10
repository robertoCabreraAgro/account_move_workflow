from odoo import api, fields, models, _
from itertools import chain
import logging

_logger = logging.getLogger(__name__)

class AccountMoveTemplate(models.Model):
    _inherit = 'account.move.template'
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    workflow_line_ids = fields.One2many(
        'account.workflow.template.line',
        'template_id',
        string='Used in Workflows'
    )
    
    def _compute_workflow_count(self):
        """Compute the number of workflows this template is used in"""
        for template in self:
            template.workflow_count = len(template.workflow_line_ids)
    
    workflow_count = fields.Integer(
        string='# Workflows',
        compute='_compute_workflow_count'
    )
    
    def action_view_workflows(self):
        self.ensure_one()
        workflows = self.workflow_line_ids.mapped('workflow_id')

        # Aplana cualquier lista anidada y filtra solo enteros válidos
        raw_ids = workflows.ids
        workflow_ids = list(
            filter(lambda x: isinstance(x, int),
                chain.from_iterable(
                    [wid if isinstance(wid, list) else [wid] for wid in raw_ids]
                ))
        )

        _logger.info("Opening workflows with IDs: %s", workflow_ids)

        action = self.env.ref('account_move_workflow.action_account_move_workflow').read()[0]

        if len(workflow_ids) == 1:
            action['views'] = [(self.env.ref('account_move_workflow.view_account_move_workflow_form').id, 'form')]
            action['res_id'] = workflow_ids[0]
        else:
            action['domain'] = [('id', 'in', workflow_ids)]

        return action

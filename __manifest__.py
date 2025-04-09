{
    'name': 'Account Move Workflow',
    "version": "saas~18.2.1.0.0",
    'category': 'Accounting',
    'summary': 'Define and execute accounting workflow templates',
    'description': """
        This module extends account_move_template functionalities to define reusable accounting workflows.
        It allows to automate repetitive operations by configuring templates with support for multiple companies,
        partners and operational contexts.
        
        Features:
        - Create multi-step accounting workflows based on existing templates
        - Define execution conditions for each template
        - Execute workflows via dedicated wizard from accounting menu or from journal entries
        - Validate data before generating moves to prevent accounting errors
        - Create relationships between generated entries for easier tracking
    """,
    'author': 'Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/account-financial-tools',
    'depends': [
        'account',
        'account_move_template',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_workflow_views.xml',
        'views/account_move_views.xml',
        'views/account_move_workflow_wizard_views.xml',
        'views/account_move_workflow_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
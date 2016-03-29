# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning, except_orm
from .account import BUDGETING_LEVEL


class AccountBudget(models.Model):
    _name = "account.budget"
    _description = "Budget"

    name = fields.Char(
        string='Name',
        required=True,
        states={'done': [('readonly', True)]},
    )
    code = fields.Char(
        string='Code',
        size=16,
        required=True,
        states={'done': [('readonly', True)]},
    )
    creating_user_id = fields.Many2one(
        'res.users',
        string='Responsible User',
        default=lambda self: self._uid,
    )
    validating_user_id = fields.Many2one(
        'res.users',
        string='Responsible User',
    )
    date_from = fields.Date(
        string='Start Date',
        compute='_compute_date',
        readonly=True,
        store=True,
    )
    date_to = fields.Date(
        string='Start Date',
        compute='_compute_date',
        readonly=True,
        store=True,
    )
    state = fields.Selection(
        [('draft', 'Draft'),
         ('cancel', 'Cancelled'),
         ('confirm', 'Confirmed'),
         ('validate', 'Validated'),
         ('done', 'Done')],
        string='Status',
        default='draft',
        index=True,
        required=True,
        readonly=True,
        copy=False,
    )
    budget_line_ids = fields.One2many(
        'account.budget.line',
        'budget_id',
        string='Budget Lines',
        states={'done': [('readonly', True)]},
        copy=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env[
            'res.company']._company_default_get('account.budget')
    )
    version = fields.Integer(
        string='Version',
        readonly=True,
        default=1,
        help="Indicate revision of the same budget plan. "
        "Only latest one is used",
    )
    latest_version = fields.Boolean(
        string='Current',
        readonly=True,
        default=True,
        # compute='_compute_latest_version',  TODO: determine version
        help="Indicate latest revision of the same plan.",
    )
    fiscalyear_id = fields.Many2one(
        'account.fiscalyear',
        string='Fiscal Year',
        required=True,
    )

    @api.one
    @api.depends('fiscalyear_id')
    def _compute_date(self):
        self.date_from = self.fiscalyear_id.date_start
        self.date_to = self.fiscalyear_id.date_stop

    @api.multi
    def _validate_budgeting_level(self):
        for budget in self:
            budgeting_level = budget.fiscalyear_id.budgeting_level
            count = self.env['account.budget.line'].search_count(
                [('budget_id', '=', budget.id), (budgeting_level, '=', False)])
            if count:
                raise except_orm(
                    _('Budgeting Level Warning'),
                    _('Required budgeting level is %s') %
                    (BUDGETING_LEVEL[budgeting_level]))

    @api.multi
    def budget_validate(self):
        self._validate_budgeting_level()
        self.write({
            'state': 'validate',
            'validating_user_id': self._uid,
        })
        return True

    @api.multi
    def budget_confirm(self):
        self._validate_budgeting_level()
        self.write({'state': 'confirm'})
        return True

    @api.multi
    def budget_draft(self):
        self.write({'state': 'draft'})
        return True

    @api.multi
    def budget_cancel(self):
        self.write({'state': 'cancel'})
        return True

    @api.multi
    def budget_done(self):
        self.write({'state': 'done'})
        return True

    # ---- BUDGET CHECK ----
    @api.model
    def get_fiscal_and_budgeting_level(self, budget_date=False):
        if not budget_date:
            budget_date = fields.Date.today()
        Fiscal = self.env['account.fiscalyear']
        fiscal_id = Fiscal.find(budget_date)
        budgeting_level = Fiscal.browse(fiscal_id).budgeting_level
        return fiscal_id, budgeting_level

    @api.model
    def _get_model_budgeting_level(self):
        MODEL_DICT = {
            'activity_group_id': 'account.activity.group',
            'activity_id': 'account.activity',
        }
        return MODEL_DICT

    @api.model
    def _get_budgeting_resource(self, budgeting_resource_id, fiscal, *args):
        model_dict = self._get_model_budgeting_level()
        model = model_dict.get(fiscal.budgeting_level, False)
        if not budgeting_resource_id:
            field = BUDGETING_LEVEL[fiscal.budgeting_level]
            raise Warning(_("Field %s is not entered, "
                            "can not check for budget") % (field,))
        # Get budget monitor of specified object, i.e., Activity Group ID
        resource = self.env[model].browse(budgeting_resource_id)
        return resource

    @api.model
    def _get_budget_monitor(self, resource, fiscal, *args):
        monitors = resource.monitor_ids.\
            filtered(lambda x: x.fiscalyear_id == fiscal)
        if not monitors:
            return False
        return monitors

    @api.model
    def check_budget(self, amount, budgeting_resource_id, fiscal_id, *args):
        res = {'budget_ok': True,
               'message': False, }
        AccountFiscalyear = self.env['account.fiscalyear']
        fiscal = AccountFiscalyear.browse(fiscal_id)
        if not fiscal.budget_control:
            return res
        resource = self._get_budgeting_resource(budgeting_resource_id,
                                                fiscal, *args)
        monitors = self._get_budget_monitor(resource, fiscal, *args)
        # Validation
        if not monitors:  # No plan
            res['budget_ok'] = False
            res['message'] = _('%s\n'
                               '[%s] the requested budget is %s,\n'
                               'but there is no budget plan for it.') % \
                (fiscal.name, resource.name_get()[0][1],
                 '{0:,}'.format(amount))
            return res
        if amount > monitors[0].amount_balance:
            res['budget_ok'] = False
            res['message'] = _('%s\n'
                               '[%s] remaining budget is %s,\n'
                               'but the requested budget is %s') % \
                (fiscal.name, resource.name_get()[0][1],
                 '{0:,}'.format(monitors[0].amount_balance),
                 '{0:,}'.format(amount))
        return res


class AccountBudgetLine(models.Model):

    _name = "account.budget.line"
    _description = "Budget Line"

    budget_id = fields.Many2one(
        'account.budget',
        string='Budget',
        ondelete='cascade',
        index=True,
        required=True,
    )
    #     analytic_account_id = fields.Many2one(
    #         'account.analytic.account',
    #         string='Analytic Account',
    #     )
    date_from = fields.Date(
        string='Start Date',
        compute='_compute_date',
        readonly=True,
        store=True,
    )
    date_to = fields.Date(
        string='End Date',
        compute='_compute_date',
        readonly=True,
        store=True,
    )
    planned_amount = fields.Float(
        string='Planned Amount',
        required=True,
        digits_compute=dp.get_precision('Account'),
    )
    company_id = fields.Many2one(
        'res.company',
        related='budget_id.company_id',
        string='Company',
        type='many2one',
        store=True,
        readonly=True,
    )
    activity_group_id = fields.Many2one(
        'account.activity.group',
        string='Activity Group',
    )
    activity_id = fields.Many2one(
        'account.activity',
        string='Activity',
        domain="['|', ('activity_group_id', '=', activity_group_id),"
        "('activity_group_id', '=', False)]"
    )
    period_id = fields.Many2one(
        'account.period',
        string='Period',
        required=True,
        domain="[('fiscalyear_id', '=', parent.fiscalyear_id)]",
    )

    @api.one
    @api.depends('period_id')
    def _compute_date(self):
        self.date_from = self.period_id.date_start
        self.date_to = self.period_id.date_stop

    @api.onchange('activity_id')
    def onchange_activity_id(self):
        self.activity_group_id = self.activity_id.activity_group_id

    #     @api.multi
    #     def create_analytic_account_activity(self):
    #         """ Create analytic account for those not been created """
    #         Analytic = self.env['account.analytic.account']
    #         for line in self:
    #             if line.activity_id:
    #                 line.analytic_account_id = \
    #                     Analytic.create_matched_analytic(line)
    #             else:
    #                 line.analytic_account_id = False
    #         return

    # class account_analytic_account(models.Model):
    #     _inherit = "account.analytic.account"
    #     budget_line_ids = fields.One2many(
    #         'account.budget.line',
    #         'analytic_account_id',
    #         string='Budget Lines',
    #     )


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
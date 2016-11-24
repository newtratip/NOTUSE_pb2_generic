# -*- coding: utf-8 -*-
from openerp import models, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if self._context.get('filter_by_invoice_ids'):
            _ids = self._context.get('filter_by_invoice_ids')
            args += ['|', ('invoice', 'in', _ids),  # For selected invoices
                     ('journal_id.type', 'not in',  # For non invoice moves
                      ['sale', 'sale_refund', 'sale_debitnote',
                       'purchase', 'purchase_refund', 'purchase_debitnote'])]
        return super(AccountMoveLine, self).search(args, offset=offset,
                                                   limit=limit, order=order,
                                                   count=count)

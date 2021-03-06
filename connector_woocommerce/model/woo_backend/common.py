# © 2009 Tech-Receptives Solutions Pvt. Ltd.
# © 2018 Serpent Consulting Services Pvt. Ltd.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
# See LICENSE file for full copyright and licensing details.

import logging

from datetime import datetime
from contextlib import contextmanager

from odoo import models, api, fields, _
from odoo.exceptions import Warning
from odoo.addons.connector.models import checkpoint
from ...components.backend_adapter import WooLocation, WooAPI

_logger = logging.getLogger(__name__)

try:
    from woocommerce import API
except ImportError:
    _logger.debug("Cannot import 'woocommerce'")


class WooBackend(models.Model):
    _name = 'woo.backend'
    _inherit = 'connector.backend'
    _description = 'WooCommerce Backend Configuration'

    name = fields.Char(string='name')
    location = fields.Char("Url")
    consumer_key = fields.Char("Consumer key")
    consumer_secret = fields.Char("Consumer Secret")
    version = fields.Selection([
                                ('v2', 'V2'),
                                ('v3', 'V3')
                                ],
                               string='Version')
    verify_ssl = fields.Boolean("Verify SSL")
    default_lang_id = fields.Many2one(
        comodel_name='res.lang',
        string='Default Language',
        help="If a default language is selected, the records "
             "will be imported in the translation of this language.\n"
             "Note that a similar configuration exists "
             "for each storeview.",
    )

    @contextmanager
    @api.multi
    def work_on(self, model_name, **kwargs):
        self.ensure_one()
        lang = self.default_lang_id
        if lang.code != self.env.context.get('lang'):
            self = self.with_context(lang=lang.code)
        woo_location = WooLocation(
            self.location,
            self.consumer_key,
            self.consumer_secret,
            self.version or 'v3'
        )
        with WooAPI(woo_location) as woo_api:
            _super = super(WooBackend, self)
            # from the components we'll be able to do: self.work.woo_api
            with _super.work_on(
                    model_name, woo_api=woo_api, **kwargs) as work:
                yield work

    @api.multi
    def add_checkpoint(self, record):
        self.ensure_one()
        record.ensure_one()
        return checkpoint.add_checkpoint(self.env, record._name, record.id,
                                         self._name, self.id)

    @api.multi
    def update_existing_order(self, woo_sale_order, data):
        """ Enter Your logic for Existing Sale Order """
        return True

    @api.multi
    def check_existing_order(self, data):
        order_ids = []
        for val in data['orders']:
            woo_sale_order = self.env['woo.sale.order'].search(
                [('external_id', '=', val['id'])])
            if woo_sale_order:
                self.update_existing_order(woo_sale_order[0], val)
                continue
            order_ids.append(val['id'])
        return order_ids

    @api.multi
    def test_connection(self):
        location = self.location
        cons_key = self.consumer_key
        sec_key = self.consumer_secret
        version = self.version or 'v3'
        msg = str()
        try:
            wcapi = API(
                url=location,  # Your store URL
                consumer_key=cons_key,  # Your consumer key
                consumer_secret=sec_key,  # Your consumer secret
                version=version,  # WooCommerce WP REST API version
                query_string_auth=True  # Force Basic Authentication as query
                                        # string true and using under HTTPS
            )
            r = wcapi.get("products")
            if r.status_code == 404:
                msg = "(Enter Valid url)"
            val = r.json()
        except:
            raise Warning(_("Sorry, Could not reach WooCommerce site! %s")\
                          % (msg))
        msg = ''
        if 'errors' in r.json():
            msg = val['errors'][0]['message'] + '\n' + \
            val['errors'][0]['code']
            raise Warning(_(msg))
        else:
            raise Warning(_('Test Success'))
        return True

    @api.multi
    def import_category(self):
        import_start_time = datetime.now()
        backend = self
        from_date = None
        self.env['woo.product.category'].with_delay(priority=1).import_batch(
                backend,
                filters={'from_date': from_date,
                         'to_date': import_start_time},
            )
        return True

    @api.multi
    def import_product(self):
        import_start_time = datetime.now()
        backend = self
        from_date = None
        self.env['woo.product.product'].with_delay(priority=2).import_batch(
                backend,
                filters={'from_date': from_date,
                         'to_date': import_start_time},
            )
        return True

    @api.multi
    def import_customer(self):
        import_start_time = datetime.now()
        backend = self
        from_date = None
        self.env['woo.res.partner'].with_delay(priority=3).import_batch(
                backend,
                filters={'from_date': from_date,
                         'to_date': import_start_time}
            )
        return True

    @api.multi
    def import_order(self):
        import_start_time = datetime.now()
        backend = self
        from_date = None
        self.env['woo.sale.order'].with_delay(priority=4).import_batch(
                backend,
                filters={'from_date': from_date,
                         'to_date': import_start_time}
            )
        return True

    @api.multi
    def import_categories(self):
        """ Import Product categories from WooCommerce site """
        for backend in self:
            backend.import_category()
        return True

    @api.multi
    def import_products(self):
        """ Import Products from WooCommerce  site """
        for backend in self:
            backend.import_product()
        return True

    @api.multi
    def import_customers(self):
        """ Import Customers from WooCommerce  site """
        for backend in self:
            backend.import_customer()
        return True

    @api.multi
    def import_orders(self):
        """ Import Orders from WooCommerce  site """
        for backend in self:
            backend.import_order()
        return True

    @api.multi
    def export_data(self, model, domain=[]):
        """
        This method create/updates the records with Odoo record
         on WooCoomerce store.
        """
        self.ensure_one()
        woo_obj = self.env["woo.%s" % model]
        target_obj = self.env[model]
        import_ids = target_obj.search(domain)
        if not import_ids:
            raise Warning(_("Sorry, There is no record to Export!"))
        # Creating Jobs
        for import_id in import_ids:
            is_woo_data = woo_obj.search([
                                ('odoo_id', '=', import_id.id)], limit=1)
            if is_woo_data:
                #Do export
                is_woo_data.with_delay().export_record()
            else:
                # Build environment to export
                import_id = woo_obj.create({
                    'backend_id': self.id,
                    'odoo_id': import_id.id,
                })
                # Do export
                import_id.with_delay().export_record()
        return True

    @api.multi
    def export_category(self):
        """
            This Method create/update the product category records
            on WooCommerce with Odoo data.
        """
        #Add filters if any here.
        domain = []
        self.export_data("product.category", domain)

    @api.multi
    def export_product(self):
        """
            This Method create/update the product records
            on WooCommerce with Odoo data.
        """
        #Add filters if any here.
        domain = [('active', '=', True)]
        self.export_data("product.product", domain)

    @api.multi
    def export_customer(self):
        """
            This Method create/update the customer records
            on WooCommerce with Odoo data.
        """
        #Add filters if any here.
        domain = [('customer', '=', True),
                  ('active', '=', True)]
        self.export_data("res.partner", domain)

    @api.multi
    def export_saleorder(self):
        """
            This Method create/update the customer records
            on WooCommerce with Odoo data.
        """
        #Add filters if any here.
        domain = []
        self.export_data("sale.order", domain)

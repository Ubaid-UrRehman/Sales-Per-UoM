# -*- coding: utf-8 -*-
from openerp import api, models, fields
from openerp.exceptions import Warning
import openerp.addons.decimal_precision as dp

import openerp.addons.product.product as native_product
from lxml import etree

class local_product_uom(models.Model):
    _inherits = {'product.uom':'uid', }
    _name = "localproduct.uom"
    uid = fields.Many2one('product.uom', ondelete='cascade', required=True)
    #This references the conversion class this product belongs to
    localcategory_id = fields.Many2one('productuom.class', 'Unit of Measure Conversion Class', required=True, ondelete='cascade', help="Conversion between Units of Measure can only occur if they belong to the same category. The conversion will be made based on the ratios.")

    #We need to delete the corresponding records in product.uom. overriding unlink() lets us do that.
    @api.multi
    def unlink(self):
        self.uid.unlink()
        return super(local_product_uom, self).unlink()

    #Here we automatically compute the normal UoM category, base on the conversion class.  The normal UoM category is part of the conversion class, so its easy to reference.
    @api.onchange('localcategory_id')
    def onchange_localcategory_id(self):
        self.category_id = self.localcategory_id.catid

    def onchange_type(self, cursor, user, ids, value):
        if value == 'reference':
            return {'value': {'factor': 1, 'factor_inv': 1}}
        return {}




class overloadproduct_uom(models.Model):
    _inherit = 'product.uom'
    #this lets us know if the UoM is sellable
    uom_sell = fields.Boolean('Sellable?', default=True)
    #this will be a hidden field that lets us filter our product specific UoM's from the normal UoM's
    islocaluom = fields.Boolean('Is a product uom?', default=False)
    #We need to make sure the name and category are unique, so we add SQL constraints
    _sql_constraints = [
        ('factor_gt_zero', 'CHECK (factor!=0)', 'The conversion ratio for a unit of measure cannot be 0!'),
        ('uom_uniq', 'UNIQUE (name,category_id)', 'Only one entry for that UOM per category')]

class overloaduom_category(models.Model):
    _inherit = 'product.uom.categ'
    #this will be a hidden field that lets us filter our UoM Conversion Categories from the normal UoM categories
    isuomclass = fields.Boolean('Is a UoM Class?', default=False)
    #We cannot allow duplicate names.  Odoo doesn't normally do this check, but it probably should.
    _sql_constraints = [('name_uniq', 'UNIQUE (name)', 'Product UOM Conversion Class must be unique.')]


class product_uom_class(models.Model):
    _inherits = {'product.uom.categ':'catid'}
    _name = 'productuom.class'
    catid = fields.Many2one('product.uom.categ', ondelete='cascade', required=True)
    #this lets us reference our product specific UoMs from the conversion class.
    localuom = fields.One2many('localproduct.uom', 'localcategory_id', 'Per Product Unit of Measure', ondelete='restrict',required=False, help="Unit of Measure used for this products stock operation.")

    @api.multi
    def unlink(self):
        self.catid.unlink()
        return super(product_uom_class, self).unlink()



class ProductTemplate(models.Model):
    _inherit = 'product.template'
    #This field will let us choose if we are using per product uom on the product
    uom_class = fields.Many2one('productuom.class', 'Per Product UOM Conversion Class', ondelete='restrict',required=False, help="Unit of Measure class for Per Product UOM")
    #These computed fields are for calculating the domain on a form edit
    calcislocaluom = fields.Boolean('Find if its a localuom',compute='_computelocaluom', store=True, default=False)
    calccatidname = fields.Char('Find the name of the category id', compute='_computecatidname', store=True,default=True)


    @api.one
    @api.depends('uom_class')
    def _computelocaluom(self):
        if (self.uom_class):
            self.calcislocaluom = True
            return True
        else:
            self.calcislocaluom = False
            return False

    @api.one
    @api.depends('uom_class')
    def _computecatidname(self):
        if (self.uom_class):
            self.calccatidname = self.uom_class.name
            return self.uom_class.name
        else:
            #Due to the conditions we later impose within the view, we need to specify a category name that will always be there
            self.calccatidname = "Unsorted/Imported Units"
            return True

    #When uom_class is changed, we need to set the uom_id and uom_po_id domain so that only uom's from our uom_class can be selected
    @api.onchange('uom_class')
    def onchange_uom_class(self):

        if (self.uom_class.catid.isuomclass == False):
            result = {'domain': {'uom_id': [('islocaluom', '=', False)], 'uom_po_id': [('islocaluom', '=', False)]}}
            self.uom_id = False
            self.uom_po_id = False

        else:
            result = { 'domain':{'uom_id':[('islocaluom','=',True),('category_id.name','=',self.uom_class.name)],'uom_po_id':[('islocaluom','=',True),('category_id.name','=',self.uom_class.name)]}}
            records = self.env['product.uom'].search([('category_id.name','=',self.uom_class.name),('name','=',self.uom_id.name)],limit=1)
            if records:
                self.uom_id = records[0]
            else:
                self.uom_id = False

            records = self.env['product.uom'].search([('category_id.name', '=', self.uom_class.name), ('name', '=', self.uom_po_id.name)], limit=1)
            if records:
                self.uom_po_id = records[0]
            else:
                self.uom_po_id = False

        return result

    #field_view_get returns the view.  This was a dead end solution for the dynamic domain problem, but the code remains in case it might be useful.

    """@api.model
    def fields_view_get(self, view_id=None, view_type=None, context=None, toolbar=False, submenu=False):

        res = super(ProductTemplate, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)

        if view_type == 'form':
            doc = etree.XML(res['arch'])

            the_uomids = doc.xpath("//field[@name='uom_id']")
            the_uomid = the_uomids[0] if the_uomids \
                else False

            the_uompoids = doc.xpath("//field[@name='uom_po_id']")
            the_uompoid = the_uompoids[0] if the_uompoids \
                else False

            obj = self.env['product.template']
            active_id = self.env.context.get('active_id', False)
            print active_id
            print context
            print self.env
            uom_class=obj.browse(active_id).uom_class
            if uom_class:
                print uom_class.name
            else:
                print "nothing found"


            print res['fields']['uom_id']
            the_uomid.set('domain',self.test)
            res['arch'] = etree.tostring(doc)
        # your modification in the view
        # result['fields'] will give you the fields. modify it if needed
        # result['arch'] will give you the xml architecture. modify it if needed
        return res"""




class NewSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    #These computed fields are for calculating the domain on a form edit
    relcatid = fields.Many2one(related='product_uom.category_id',store=True)

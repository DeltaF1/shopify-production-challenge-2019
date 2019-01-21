import json
import random
import string

import web

# A mapping of URI's to handlers
urls = (
    '/product/(\d+)', 'product',
    '/products', 'products',
    '/cart', 'create_cart',
    '/cart/(\d+)', 'cart',
    '/cart/(\d+)/complete', 'cart_complete',
    '/authenticate', 'authenticate'
)

db = web.database(dbn="sqlite", db="shop.db")

def set_json_headers():
    web.header('Content-Type', 'application/json')

class product:
    def GET(self, id):
        data = db.select('products', where={'id':id})
        if data:
            set_json_headers()
            return json.dumps(list(data))
        else:
            web.ctx.status = "404 Product Not Found"
            return None
        
class products:
    def GET(self):
        query = web.input(only_in_stock="0")
        
        # Adds a clause to only display in-stock items
        if query.only_in_stock == "1":
            data = db.select('products', where="inventory > 0")
        else:
            data = db.select('products')
        
        products = list(data)
        
        set_json_headers()
        return json.dumps(products)

class create_cart:
    def generate_cookie(self, n=6):
        """
        Generate a random string to act as a session cookie.
        
        WARNING: IN PRODUCTION THIS SHOULD BE IMPLEMENTED USING
        A CRPYOTGRAPHICALLY STRONG RANDOM NUMBER GENERATOR. THIS
        IS SOLELY A PROOF OF CONCEPT.
        """
        return ''.join(random.choices(string.ascii_letters+string.digits, k=n))

    def create_cart(self, cookie):
        id = db.insert('carts', cookie=cookie)
        return id
        
    def POST(self):
        # get the current session cookie, or generate a new one
        token = web.cookies().get("session_token")
        if not token:
            token = self.generate_cookie()
        web.setcookie("session_token", token, 600)
        id = self.create_cart(token)
        
        set_json_headers()
        return json.dumps({'id':id})


def validate_session(function):
    """
    A wrapper to validate the session cookie against the requested cart.
    """
    def validated_func(self, cart_id):
        cookie = web.cookies().get("session_token")
        if self.check_ownership(cart_id, cookie):
            return function(self, cart_id)
        else:
            # If the current session is not authorized to view/modify
            # the requested cart:
            web.ctx.status = '404 Cart not found'
            web.header('Content-Type', 'plain/text')
            return "POST /cart to create a new cart and receive a session cookie"
    
    return validated_func  
    
class cart:
    def get_cart_contents(self, id):
        data = db.query(
            'SELECT product_id as id, price, quantity, title FROM cart_contents JOIN products ON cart_contents.product_id=products.id WHERE cart_contents.cart_id = $id',
            vars = {'id':id}
        )
        return list(data)
            
    def set_cart_contents(self, id, product_id, quantity):
        # If the product exists
        if db.select('products', where={'id':product_id}):
            if db.select('cart_contents', where={'cart_id':id, 'product_id':product_id}):
                db.update('cart_contents', where={'cart_id':id, 'product_id':product_id}, quantity=quantity)
            else:
                db.insert('cart_contents', cart_id=id, product_id=product_id, quantity=quantity)
            db.query("DELETE FROM cart_contents WHERE quantity <= 0")
        else:
            web.ctx.status = "422 Product Not Found"
            
    def check_ownership(self, id, cookie):
        data = db.select('carts', where={'id':id, 'cookie':cookie})
        return bool(data)
       
    @validate_session
    def GET(self, id):
        data = db.select('cart_contents', what='product_id as id, quantity', where={'cart_id':id})
        contents = self.get_cart_contents(id)
        cart = {
            'id':id,
            'contents':contents,
            'price':sum([p['price']*p['quantity'] for p in contents])
        }
        
        set_json_headers()
        return json.dumps(cart)

    @validate_session
    def PATCH(self, id):
        body = json.loads(web.data())
        
        contents_row = db.select('cart_contents', what='quantity', where={'cart_id':id, 'product_id':body['id']})
        try:
            prev_quantity = contents_row[0]['quantity']
        except IndexError:
            prev_quantity = 0
        
        return self.set_cart_contents(id, body['id'], prev_quantity+body['quantity']) 
 
    @validate_session
    def PUT(self, id):
        body = json.loads(web.data())
        return self.set_cart_contents(id, body['id'], body['quantity'])
    
class cart_complete(cart):
    @validate_session
    def POST(self, id):
        cart_contents = self.get_cart_contents(id)
        
        # check to make sure the cart is purchaseable
        
        # NOTE: In a distributed system this part would need to have a write lock on
        # the inventory table to prevent a race condition
        product_rows = []
        failed_to_buy = []
        for product in cart_contents:
            product_row = db.select("products", what="id, inventory", where={'id':product["id"]})[0]
            product_rows.append(product_row)
            
            # Check to make sure that there is sufficient inventory to purchase the requested quantity
            if product_row["inventory"] < product["quantity"]:
                failed_to_buy.append({'id':product["id"],
                'diff':product["quantity"] - product_row["inventory"]})
        
        if failed_to_buy:
            web.ctx.status = "400 Insufficient Inventory"
            set_json_headers()
            return json.dumps(failed_to_buy)
        
        # Decrease inventory
        for i, product in enumerate(product_rows):
            db.update("products", where={'id':product["id"]}, inventory=product["inventory"]-cart_contents[i]["quantity"])
        
        cart = self.GET(id)
        db.delete('carts', where={'id':id})
        return cart

            
if __name__ == '__main__':
    app = web.application(urls, globals(), autoreload=True)
    app.internalerror = web.debugerror
    app.run()
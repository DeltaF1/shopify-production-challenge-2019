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
        
        set_json_headers()
        return json.dumps(list(data))
        
        
class products:
    def GET(self):
        query = web.input(only_in_stock="0")
        
        if query.only_in_stock == "1":
            data = db.select('products', where="inventory > 0")
        else:
            data = db.select('products')
        
        products = []
        
        for product in data:
            products.append(product)
        
        set_json_headers()
        return json.dumps(products)

class create_cart:
    def generate_cookie(self), n=6:
        """
        Generate a random string to act as a session cookie.
        
        WARNING: IN PRODUCTION THIS SHOULD BE IMPLEMENTED USING
        A CRPYOTGRAPHICALLY STRONG RANDOM NUMBER GENERATOR. THIS
        IS SOLELY A PROOF OF CONCEPT.
        """
        return ''.join(random.choice(string.ascii_letters+string.digits, k=n))

    def create_cart(self, cookie):
        id = db.insert('carts', cookie=cookie)
        return id
        
    def POST(self):
        # get the current session cookie, or 
        cookie = web.cookies(session_token=generate_cookie())
        web.setcookie("session_token", cookie, 600)
        id = self.create_cart(cookie)
        
        set_json_headers()
        return json.dumps({'id':id})


def validate_session(function):
    def validated_func(self, id):
        cookie = web.cookies.get("session_token")
        if self.check_ownership(id, cookie):
            function(self, id)
        else:
            web.ctx.status = '401 Unauthorized'
            return "POST /cart to create a new cart and receive a session cookie"
    
    return validated_func  
    
class cart:
    def get_cart_contents(self, id):
        data = db.query(
            'SELECT product_id as id, price, quantity, title FROM cart_contents JOIN products ON cart_contents.product_id=products.id WHERE cart_contents.cart_id = $id',
            vars = {'id':id}
        )
        return list(data)
            
    def check_ownership(self, id, cookie):
        data = db.select('carts', where={'id':id, 'cookie':cookie})
        return len(list(data)) > 0
       
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
    
    def set_cart_contents(self, id, product_id, quantity):
        try:
            db.update('cart_contents', where={'cart_id':id, 'product_id':product_id}, quantity=quantity)
        except:
            db.insert('cart_contents', cart_id=id, product_id=product_id, quantity=quantity)
        db.query("DELETE FROM cart_contents WHERE quantity <= 0")    
    
    
    @validate_session
    def PATCH(self, id):
        body = json.loads(web.data())
        
        # if "id" not in body:
        #     web.ctx.status = '400 Bad Request'
        #     return "Body should be in the form of a json object with fields id and quantity."
        
        try:
            inventory = (
                    db.select('cart_contents', what='quantity', where={'cart_id':id, 'product_id':body['id']})
                )[0]['quantity']
        except IndexError:
            inventory = 0
            
        self.set_cart_contents(id, body['id'], inventory+body['quantity']) 
        return None
 
        
    @validate_session
    def PUT(self, id):
        body = json.loads(web.data())
        self.set_cart_contents(id, body['id'], body['quantity'])
    
class cart_complete(cart):
    def POST(self, id):
        cookie = "cookie"
        if self.check_ownership(id, cookie):
            cart_contents = self.get_cart_contents(id)
            
            # check to make sure the cart is purchaseable
            
            # in a distributed system this part would need to have a write lock on
            # the inventory table to prevent a race condition
            product_rows = []
            for product in cart_contents:
                product_row = db.select("products", what="id, inventory", where={'id':product["id"]})[0]
                product_rows.append(product_row)
                
                # Check to make sure that there is sufficient inventory to purchase the requested quantity
                if product_row["inventory"] < product["quantity"]:
                    web.ctx.status = '400 Insufficient inventory'
                    return None
            
            # Decrease inventory
            for i, product in enumerate(product_rows):
                db.update("roducts", where={'id':product["id"]}, inventory=product["inventory"]-cart_contents[i]["quantity"])
            
            db.delete('carts', where={'id':id})
            return None
        else:
            web.ctx.status = '401 Unauthorized'
            return None
            
if __name__ == '__main__':
    app = web.application(urls, globals(), autoreload=True)
    app.internalerror = web.debugerror
    app.run()
CREATE TABLE IF NOT EXISTS products (
	id INTEGER PRIMARY KEY,
	title VARCHAR,
	price DOUBLE,
	inventory INT
);

CREATE TABLE IF NOT EXISTS carts (
	id INTEGER PRIMARY KEY,
	cookie VARCHAR
);

CREATE TABLE IF NOT EXISTS cart_contents (
	cart_id INT,
	product_id INT,
	quantity INT,
	CONSTRAINT fk_carts
		FOREIGN KEY (cart_id)
		REFERENCES carts(id)
		ON DELETE CASCADE,
	CONSTRAINT fk_products
		FOREIGN KEY (product_id)
		REFERENCES products(id)
		ON DELETE CASCADE
);
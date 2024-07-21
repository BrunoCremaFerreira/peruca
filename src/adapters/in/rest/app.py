from flask import Flask, request
from flask_restx import Api, Resource, fields

app = Flask(__name__)
api = Api(app, version='1.0', title='Peruca LLM Assistant',
          description='Peruca LLM Assistant',
          )

ns_talk = api.namespace('talk', description='Operations related to talk')

item_model = api.model('Item', {
    'id': fields.Integer(readOnly=True, description='The unique identifier of an item'),
    'name': fields.String(required=True, description='Item name'),
    'price': fields.Float(required=True, description='Item price')
})

ITEMS = []

@ns_talk.route('/')
class ItemList(Resource):
    # Shows a list of all items, and lets you POST to add new items

    @ns_talk.doc('list_items')
    @ns_talk.marshal_list_with(item_model)
    def get(self):
        """List all items"""
        return ITEMS

    @ns_talk.doc('create_item')
    @ns_talk.expect(item_model)
    @ns_talk.marshal_with(item_model, code=201)
    def post(self):
        """Create a new item"""
        item = api.payload
        item['id'] = len(ITEMS) + 1
        ITEMS.append(item)
        return item, 201

@ns_talk.route('/<int:id>')
@ns_talk.response(404, 'Item not found')
@ns_talk.param('id', 'The item identifier')
class Item(Resource):
    """Show a single item and lets you delete them"""
    @ns_talk.doc('get_item')
    @ns_talk.marshal_with(item_model)
    def get(self, id):
        """Fetch a given resource"""
        for item in ITEMS:
            if item['id'] == id:
                return item
        api.abort(404, "Item {} doesn't exist".format(id))

    @ns_talk.doc('delete_item')
    @ns_talk.response(204, 'Item deleted')
    def delete(self, id):
        """Delete a item given its identifier"""
        global ITEMS
        ITEMS = [item for item in ITEMS if item['id'] != id]
        return '', 204
    
if __name__ == '__main__':
    app.run(debug=True)

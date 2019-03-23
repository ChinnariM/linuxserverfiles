from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Items
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests


app = Flask(__name__)

CLIENT_ID = json.loads(
    open('/var/www/ItemCatalogProject/ItemCatalogProject/client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "CATALOG APP."


engine = create_engine(
    'sqlite:///catalog.db',
    connect_args={
        'check_same_thread': False})
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# Create anti-forgery state token
@app.route('/login')
def showLogin():
    # redirect to log in page
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in range(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('/var/www/ItemCatalogProject/ItemCatalogProject/client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print("Token's client ID does not match app's.")
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(
            json.dumps('Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']


    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print("done!")
    return output

# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session['access_token']
    print('In gdisconnect access token is %s', access_token)
    print('User name is: ')
    print(login_session['username'])
    if access_token is None:
        #print('Access Token is None')
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print('result is ')
    print(result)
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:

        response = make_response(
            json.dumps(
                'Failed to revoke token for given user.',
                400))
        response.headers['Content-Type'] = 'application/json'


# Task 1: Display all the Categories and the latest added items.
@app.route('/')
@app.route('/catalog')
def showCatalog():
    showcategory = session.query(Category).all()
    showlatestitems = session.query(
        Items.title,
        Category.name).join(Category).order_by(
        Items.id.desc())
    # print(showlatestitems)
    if 'username' not in login_session:
        return render_template(
            'publiccatalog.html',
            showcategory=showcategory,
            showlatestitems=showlatestitems)
    else:
        return render_template(
            'catalog.html',
            showcategory=showcategory,
            showlatestitems=showlatestitems)

# Task 2: once user clicks on any Category it will system will list the
# items for that Category
@app.route('/<string:name>/items')
@app.route('/catalog/<string:name>/items')
def showCategoryitems(name):
    categoryitems = session.query(Category).all()
    category = session.query(Category).filter(name == Category.name).one()
    showitemCount = session.query(
        Items.id).join(Category).filter(
        name == Category.name).count()
    showListcategoryitems = session.query(
        Items.title, Category.name).join(Category).filter(
        name == Category.name)
    print(showListcategoryitems)
    print(showitemCount)
    return render_template(
        'category.html',
        showitemCount=showitemCount,
        categoryitems=categoryitems,
        category=category,
        showListcategoryitems=showListcategoryitems)

# Task 3: User clicks on any listed item form the category search the user
# will redirect to the Items description page
@app.route('/<string:name>/<string:title>')
def showitemdescrpition(name, title):
    # categoryitems=session.query(Category).all()
    category = session.query(Category).filter(name == Category.name).one()
    itemtitle = session.query(Items).filter(title == Items.title).one()
    # itemdescription=session.query(Items.description).filter(title==Items.title)
    if 'username' not in login_session:
        return render_template(
            'publicitemsdesc.html',
            itemtitle=itemtitle,
            category=category)
    else:
        return render_template(
            'itemsdesc.html',
            itemtitle=itemtitle,
            category=category)


# Task 4: Create route for newItem function here
@app.route('/catalog/items/new/', methods=['GET', 'POST'])
def newItem():
    if request.method == 'POST':
        newItem = Items(
            title=request.form['title'],
            description=request.form['description'],
            category_id=request.form['categories_name'])
        print(newItem)
        session.add(newItem)
        session.commit()
        flash('New  %s Item Successfully Created' % (newItem.title))
        return redirect(url_for('showCatalog'))
    else:
        return render_template('newitem.html')

# Task 5: Create route for EditItem function here
@app.route('/catalog/<string:title>/edit/', methods=['GET', 'POST'])
def editItem(title):
    if 'username' not in login_session:
        return redirect('/login')
    # category=session.query(Category).filter(name==Category.name).one()
    editedItem = session.query(Items).filter(title == Items.title).one()
    print(editedItem)
    if editedItem.user_id != login_session['email']:
        redirect(url_for('showCatalog'))

    if request.method == 'POST':
        if request.form['title']:
            editedItem.title = request.form['title']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['categories_name']:
            editedItem.catagory_id = request.form['categories_name']
        session.add(editedItem)
        session.flush()
        session.commit()
        flash(' Item Successfully Edited')
        return redirect(url_for('showCatalog'))
    else:
        return render_template('edititem.html', title=title, item=editedItem)

# Task 6: Create route for DeleteItem function here
@app.route('/catalog/<string:title>/delete/', methods=['GET', 'POST'])
def deleteItem(title):
    itemToDelete = session.query(Items).filter(title == Items.title).one()
    print(itemToDelete)
    if itemToDelete.user_id != login_session['email']:
        redirect(url_for('showCatalog'))

    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash(' Item Successfully Deleted')
        return redirect(url_for('showCatalog'))
    else:
        return render_template(
            'deleteItem.html',
            title=title,
            item=itemToDelete)


# task 7 : Creating Json End point
@app.route('/catalog.json', methods=['GET', 'POST'])
def all_catalogs():
    if request.method == 'GET':
        catalog = session.query(Category).all()
        category_list = [c.serialize for c in catalog]
        for c in range(len(category_list)):
            items = session.query(Items).filter_by(
                category_id=category_list[c]["id"])
            items_list = [i.serialize for i in items]
            if items_list:
                category_list[c]["categories"] = items_list
        return jsonify(catalog=category_list)

# Task 8 : Creating Json End point to return items for a specific Category
@app.route('/catalog/<int:category_id>.json')
@app.route('/catalog/<int:category_id>/items.json')
def showCategoryJSON(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    items = session.query(Items).filter_by(
        category_id=category_id).all()
    return jsonify(Items=[i.serialize for i in items])

# Creating Json End point to return itembased on the ID provided  for a
# specific Category id
@app.route('/catalog/<int:catalog_id>/items/<int:item_id>.json')
def showCategoryItemJSON(catalog_id, item_id):
    item = session.query(Items).filter_by(id=item_id).first()
    return jsonify(item=[item.serialize])


if __name__ == '__main__':

    app.secret_key = 'testing linux server'
    app.debug = True
    app.run()

import os
import re
import random
import hashlib
import hmac
from string import letters

import webapp2
import jinja2

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

DEBUG = True
secret = 'zkan'

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

class WikiHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))

def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)


##### user stuff
def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)

class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u


##### wiki stuff

def pages_key(name = 'default'):
    return db.Key.from_path('pages', name)

class Page(db.Model):
    name = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)

    @classmethod
    def by_name(cls, name):
        p = Page.all().filter('name =', name).get()
        return p
    
    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("page.html", p = self)

class PageHistory(db.Model):
    name = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True) 

#class BlogFront(BlogHandler):
#    def get(self):
#        posts = greetings = Post.all().order('-created')
#        self.render('front.html', posts = posts)

#class PostPage(BlogHandler):
#    def get(self, post_id):
#        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
#        post = db.get(key)
#
#        if not post:
#            self.error(404)
#            return
#
#        self.render("permalink.html", post = post)

#class NewPost(BlogHandler):
#    def get(self):
#        if self.user:
#            self.render("newpost.html")
#        else:
#            self.redirect("/login")
#
#    def post(self):
#        if not self.user:
#            self.redirect('/blog')
#
#        subject = self.request.get('subject')
#        content = self.request.get('content')
#
#        if subject and content:
#            p = Post(parent = blog_key(), subject = subject, content = content)
#            p.put()
#            self.redirect('/blog/%s' % str(p.key().id()))
#        else:
#            error = "subject and content, please!"
#            self.render("newpost.html", subject=subject, content=content, error=error)


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)

class Signup(WikiHandler):
    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username,
                      email = self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError

#class Unit2Signup(Signup):
#    def done(self):
#        self.redirect('/unit2/welcome?username=' + self.username)

class Register(Signup):
    def done(self):
        #make sure the user doesn't already exist
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup-form.html', error_username = msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

        self.login(u)
        self.redirect('/')

class Login(WikiHandler):
    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error = msg)

class Logout(WikiHandler):
    def get(self):
        self.logout()
        self.redirect('/')

class EditPage(WikiHandler):
    def get(self, page_name):
        if self.user:
            username = self.user.name
        else:
            username = None

        p = Page.by_name(page_name)
        if p:
            self.render('edit-page-form.html', username = username, 
                                               page_name = page_name, 
                                               page_content = p.content)
        else:
            if username:
                self.render('edit-page-form.html', username = username, 
                                                   page_name = page_name)
            else:
                self.redirect('/login')

    def post(self, page_name):
        name = self.request.get('name')
        content = self.request.get('content')

        p = Page(parent = pages_key(),
                 name = name, 
                 content = content)
        p.put()
        self.redirect('/')

class WikiPage(WikiHandler):
    def get(self, page_name):
        if self.user:
            username = self.user.name
        else:
            username = None

#        self.write(page_name)
        p = Page.by_name(page_name)
        if p:
            self.render('page.html', username = username, 
                                     page_name = page_name, 
                                     page_content = p.content)
        else:
            if username:
                self.redirect('/_edit' + page_name)
            else:
                self.redirect('/login')

        self.render('page.html', username = username, 
                                 page_name = page_name)

#    def post(self, page_name):
#        pass


PAGE_RE = r'(/(?:[a-zA-Z0-9_-]+/?)*)'
app = webapp2.WSGIApplication([('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ('/_edit' + PAGE_RE, EditPage),
                               ('/_edit' + PAGE_RE, EditPage),
                               (PAGE_RE, WikiPage),
                               ],
                              debug = DEBUG)


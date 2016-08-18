import os
import re
from string import letters
import random

import webapp2
import jinja2
import hmac

from google.appengine.ext import db

# for jinja templates
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)


def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)                        

# Cookie functions
def make_hash(s):
    return hmac.new(SECRET, s).hexdigest()

def make_cookie(s):
    return '%s|%s' % (s, make_hash(s))

# checks and returns if the cookie is valid
def check_cookie(cookie):
    val = cookie.split('|')[0]
    if cookie == make_cookie(val):
        return val

def get_user_id(self):
    cookie = self.request.cookies.get('user_id')
    if cookie and check_cookie(cookie):
        return cookie.split('|')[0]


# password hashing
# for hashing, not to include in production
SECRET = '142arsgdf354rasf3q451afsd'

def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hmac.new(SECRET, name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def check_pw_hash(name, pw, pw_hash):
    salt = pw_hash.split(',')[0]
    return pw_hash == make_pw_hash(name, pw, salt)


# Databases
class User(db.Model):
    ''' database for users '''
    username = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.EmailProperty(required = False)
    
    @classmethod
    def by_name(cls, name):
        u = cls.all().filter('username =', name).get()
        return u
    
    @classmethod
    def register(cls, username, pw, email = None):
        pw_hash = make_pw_hash(username, pw)
        return User(username = username,
                    pw_hash = pw_hash,
                    email = email)

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

class Blog(db.Model):
    ''' database for blogs '''
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    author = db.StringProperty(required = True)
    likes = db.IntegerProperty(default=0)
    created = db.DateTimeProperty(auto_now_add = True)

    # Keeps the white space formatting
    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str('post.html', p = self)

def comment_key(name = 'default'):
    return db.Key.from_path('comments', name)

class Comment(db.Model):
    ''' database for comments '''
    blog_id = db.StringProperty(required = True)
    author = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)

    @classmethod
    def by_blog(cls, blog_id):
        c = cls.all().filter('blog_id =', blog_id).get()
        return c

    # Keeps the white space formatting
    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str('comment.html', comment = self)



class Handler(webapp2.RequestHandler):
    ''' Main handler, rendering functions '''
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))
    
    def set_cookie(self, name, val):
        cookie = make_cookie(val)
        self.response.headers.add_header('Set-Cookie', '%s=%s; Path=/' % (name, str(cookie)))
    
    def login(self, user):
        self.set_cookie('user_id', user)
    
    # deletes cookie
    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')
    


# Regex to check signup info 
USER_RE = re.compile(r'^[a-zA-Z0-9_-]{3,20}$')
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r'^.{3,20}$')
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)       

class SignupHandler(Handler):
    def get(self):
        user_id = get_user_id(self)
        self.render('signup.html', user_id = user_id)
    
    def post(self):
        have_error = False
        username = self.request.get('username').lower()
        password = self.request.get('password')
        verify = self.request.get('verify')
        email = self.request.get('email')

        params = dict(username = username, email = email)

        if not valid_username(username):
            params['error_username'] = 'Invalid Username'
            have_error = True
        if User.by_name(username):
            params['error_username'] = 'Username already taken'
            have_error = True

        if not valid_password(password):
            params['error_password'] = 'Invalid Password'
            have_error = True
        if password != verify:
            params['error_password'] = 'Passwords do not match'
            params['error_verify'] = params['error_password']
            have_error = True
        
        if not valid_email(email):
            params['error_email'] = 'Invalid email'
            have_error = True
        
        if have_error:
            self.render('signup.html', **params)
        else:
            u = User.register(username, password, email = None)
            u.put()
            self.set_cookie('user_id', username)
            self.redirect('/')


class LoginHandler(Handler):
    def get(self):
        username = self.request.get('username')
        wrong_id = self.request.get('wrong_id')
        self.render('login.html', username = username, wrong_id = wrong_id)
    
    def post(self):
        error = ''
        username = self.request.get('username').lower()
        password = self.request.get('password')
        
        u = User.by_name(username)

        if not u:
            error = 'Username does not exist'
        
        if u and not check_pw_hash(u.username, password, u.pw_hash):
            error = 'Incorrect password'

        if not username or not password:
            error = 'All fields required'
        
        if error:
            self.render('login.html', error = error)
        else:
            self.set_cookie('user_id', username)
            self.redirect('/')
                
    
class LogoutHandler(Handler):
    def get(self):
        self.logout()
        self.redirect('/')


class NewPostHandler(Handler):
    def get(self):
        user_id = get_user_id(self)
        if not user_id:
            self.redirect('/')
        else:
            self.render('newpost.html', user_id = user_id)
    
    def post(self):
        subject = self.request.get('subject')
        content = self.request.get('content')
        author = get_user_id(self)

        if subject and content:
            b = Blog(parent = blog_key(), subject = subject, content = content, author = author)
            b.put()
            self.redirect('/blog/%s' % str(b.key().id()))
        else:
            error = 'Both fields are required'
            self.render('newpost.html', error = error)
            

class PostPage(Handler):
    def get(self, post_id):
        key = db.Key.from_path('Blog', int(post_id), parent=blog_key())
        post = db.get(key)
        user_id = get_user_id(self)
        comments = Comment.gql('WHERE blog_id = :1 ORDER BY created ASC', post_id)
        
        if not post:
            self.error(404)
            return
        
        if comments:
            self.render('permalink.html', post = post, user_id = user_id, comments = comments)
        else:
            self.render('permalink.html', post = post, user_id = user_id)
    
    def post(self, post_id):
        key = db.Key.from_path('Blog', int(post_id), parent=blog_key())
        post = db.get(key)
        author = get_user_id(self)
        content = self.request.get('content')
        likes = self.request.get('like')
        if likes:
            post.likes = int(likes) + post.likes
            post.put()
        if content and author:
            c = Comment(parent = comment_key(), blog_id = post_id, author = author, content = content, likes = likes    )
            c.put()
            comments = Comment.gql('WHERE blog_id = :1 ORDER BY created ASC', key)
            self.render('permalink.html', post = post, user_id = author, comments = comments)
        else:
            login_error = "Please login to comment"
            self.render('login.html', login_error = login_error)
        
        

    
class EditPost(Handler):
    def get(self, post_id):
        key = db.Key.from_path('Blog', int(post_id), parent=blog_key())
        post = db.get(key)
        user_id = get_user_id(self)

        # make sure logged in user is the author
        if post.author == user_id:
            self.render('editpost.html', post = post, user_id = user_id)
        else:
            error = True
            self.redirect('/login?username=%s&wrong_id=%s' % (post.author, error))

    def post(self, post_id):
        key = db.Key.from_path('Blog', int(post_id), parent=blog_key())
        post = db.get(key)
        subject = self.request.get('subject')
        content = self.request.get('content')
        if subject and content:
            post.subject = subject
            post.content = content
            post.put()
            self.redirect('/')
        else:
            error = 'Both a subject and content is required'
            self.render('editpost.html', post = post, error = error)


class DeletePost(Handler):
    def get(self, post_id):
        key = db.Key.from_path('Blog', int(post_id), parent=blog_key())
        post = db.get(key)
        user_id = get_user_id(self)
        
        # make sure logged in user is the author
        if post.author == user_id:
            self.render('delete.html', post = post, user_id = user_id)
        else:
            error = True
            self.redirect('/login?username=%s&wrong_id=%s' % (post.author, error))
    
    def post(self, post_id):
        key = db.Key.from_path('Blog', int(post_id), parent=blog_key())
        post = db.get(key)
        user_id = get_user_id(self)
        delete = self.request.get('delete')
        if post.author == user_id and delete:
            post.delete()
        self.redirect('/')


# Home page which shows all blogs
class HomePageHandler(Handler):
    def get(self):
        user_id = get_user_id(self)
        posts = Blog.all().order('-created')
        self.render('home.html', user_id = user_id, posts = posts)
    
    # to handle likes on the front page
    def post(self):
        user_id = get_user_id(self)
        posts = Blog.all().order('-created') 
        like = self.request.get('like')
        
        # make sure valid user logged in
        if user_id and like:
            post_id = self.request.get('post_id')
            key = db.Key.from_path('Blog', int(post_id), parent=blog_key())
            post = db.get(key)
            post.likes += int(like)
            post.put()
            self.render('home.html', user_id = user_id, posts = posts)
        else:
            login_error = "Please login to rate"
            self.render('login.html', login_error = login_error)



app = webapp2.WSGIApplication([
    ('/', HomePageHandler),
    ('/login', LoginHandler),
    ('/logout', LogoutHandler),
    ('/signup', SignupHandler),
    ('/newpost', NewPostHandler),
    ('/blog/([0-9]+)', PostPage),
    ('/blog/([0-9]+)/edit', EditPost),
    ('/blog/([0-9]+)/delete', DeletePost),
], debug=True)

#!/usr/bin/python

from json  import loads
from Httpy import Httpy
from time  import sleep, strftime, gmtime, time as timetime
from sys   import stderr

class Child(object):
	def __init__(self, json=None):
		self.id        = ''
		self.subreddit = ''
		self.created   = 0
		self.author    = ''
		self.ups       = 0
		self.downs     = 0
		if json != None:
			self.from_json(json)
	def from_json(self, json):
		self.id        = json['id'].rjust(6, '0')
		self.subreddit = json['subreddit']
		self.created   = int(json['created_utc'])
		self.author    = json['author']
		self.ups       = json['ups']
		self.downs     = json['downs']
		self.comments = []
		if 'replies' in json and type(json['replies']) == dict:
			for child in json['replies']['data']['children']:
				self.comments.append(Comment(child['data']))
	def __str__(self):
		return 'Reddit.%s(%s)' % (type(self).__name__, str(self.__dict__))
	def __repr__(self):
		return self.__str__()

class Post(Child,object):
	def __init__(self, json=None):
		super(Post, self).__init__(json=json)
		self.over_18  = False
		self.url      = ''
		self.selftext = None
		self.title    = ''
		if json != None:
			self.from_json(json)
	def from_json(self, json):
		super(Post,self).from_json(json)
		self.url       = Reddit.asciify(json['url'])
		self.selftext  = Reddit.asciify(json['selftext']) if json['is_self'] else None
		self.title     = Reddit.asciify(json['title'])
		
	def permalink(self):
		if self.subreddit != '':
			return 'http://reddit.com/r/%s/comments/%s' % (self.subreddit, self.id)
		else:
			return 'http://reddit.com/comments/%s' % self.id

class Comment(Child,object):
	def __init__(self, json=None):
		super(Comment, self).__init__(json=json)
		self.body     = ''
		self.post_id  = ''
		if json != None:
			self.from_json(json)
	def from_json(self, json):
		super(Comment,self).from_json(json)
		self.body    = Reddit.asciify(json['body'])
		self.post_id = json['link_id']
	def permalink(self):
		if self.subreddit != '':
			return 'http://reddit.com/r/%s/comments/%s/_/%s' % (self.subreddit, self.post_id.replace('t3_',''), self.id)
		else:
			return 'http://reddit.com/comments/%s/_/%s' % (self.post_id.replace('t3_',''), self.id)

class User(object):
	def __init__(self):
		self.name    = ''
		self.created = 0
		self.comm_karma = 0
		self.link_karma = 0

''' Retrieve posts/comments from reddit '''
class Reddit(object):
	logger = stderr
	httpy = Httpy(user_agent='user ripper by /u/4_pr0n, or contact admin@rarchives.com')
	last_request = 0.0
	modhash = None
	user_id = None

	@staticmethod
	def asciify(text):
		return text.encode('UTF-8').decode('ascii', 'ignore')

	@staticmethod
	def debug(text):
		tstamp = strftime('[%Y-%m-%dT%H:%M:%SZ]', gmtime())
		text = '%s Reddit: %s' % (tstamp, text)
		Reddit.logger.write('%s\n' % text)
		if Reddit.logger != stderr:
			stderr.write('%s\n' % text)
	
	'''
		Parses reddit response.
		Returns either:
			Post - if link is to a post
			     - Comments will be contained within Post.comments
			List of objects - if link is to a list
	'''
	@staticmethod
	def parse_json(json):
		if type(json) == list:
			# First item is post
			post = Post(json[0]['data']['children'][0]['data'])
			# Other items are comment replies to post
			post.comments = []
			for child in json[1:]:
				post.comments.extend(Reddit.parse_json(child))
			return post
		elif type(json) == dict:
			result = []
			for item in json['data']['children']:
				if item['kind'] == 't3':
					# Post
					result.append(Post(item['data']))
				elif item['kind'] == 't1':
					# Comment
					result.append(Comment(item['data']))
			return result
		raise Exception('unable to parse:\n%s' % str(json))

	'''
		Prevent API rate limiting.
		Wait until current time - last request >= 2 seconds
	'''
	@staticmethod
	def wait():
		now = float(timetime())
		if now - Reddit.last_request < 2:
			sleep(2 - (now - Reddit.last_request))
		Reddit.last_request = float(timetime())

	@staticmethod
	def login(user, password):
		Reddit.httpy.clear_cookies()
		d = {
				'user'   : user,
				'passwd' : password,
				'api_type' : 'json'
			}
		r = str(Reddit.httpy.oldpost('https://www.reddit.com/api/login/%s' % user, d), 'utf-8')
		if 'WRONG_PASSWORD' in r:
			raise Exception('login: invalid password')
		if 'RATELIMIT' in r:
			raise Exception('login: rate limit')
		try:
			json = loads(r)
		except Exception as e:
			raise Exception('login: failed to parse response: %s' % r)
		if not 'json' in json or not 'data' in json['json']:
			raise Exception('login: failed: %s' % r)
		if 'modhash' in json['json']['data']:
			Reddit.modhash = json['json']['data']['modhash']
		# Logged in
		Reddit.debug('logged in')

	@staticmethod
	def get(url):
		results = []
		Reddit.debug('loading %s' % url)
		Reddit.wait()
		try:
			r = Reddit.httpy.get(url)
			json = loads(str(r, 'utf-8'))
		except Exception as e:
			Reddit.debug('exception: %s' % str(e))
			raise e
		return Reddit.parse_json(json)
		
		
	@staticmethod
	def get_user(user, since=None, max_pages=None):
		""" 
			Get all comments and posts for a user since 'since'.
			'since' is either a post id or comment id
		"""
		results = []
		url = 'http://www.reddit.com/user/%s.json' % user
		Reddit.debug('loading %s' % url)
		Reddit.wait()
		try:
			r = Reddit.httpy.get(url)
		except Exception as e:
			Reddit.debug('exception: %s' % str(e))
			raise e
		if r.strip() == '':
			# User is deleted
			raise Exception('user is deleted')
		page = 1
		while True:
			try:
				json = loads(str(r, 'utf-8'))
			except Exception as e:
				Reddit.debug('failed to load JSON: %s\n%s' % (str(e), r))
				return results
			if 'error' in json and json['error'] == 404:
				raise Exception('account %s is deleted (404)' % user)
			for item in Reddit.parse_json(json):
				if item.id == since:
					return results
				results.append(item)
			if not 'after' in json['data'] or json['data']['after'] == None:
				Reddit.debug('get: hit end of posts/comments')
				break
			after = json['data']['after']
			if max_pages != None and max_pages >= page: break
			next_url = '%s?after=%s' % (url, after)
			Reddit.debug('loading %s' % next_url)
			Reddit.wait()
			r = Reddit.httpy.get(next_url)
			page += 1
		return results

	@staticmethod
	def get_links_from_text(text):
		''' Returns list of URLs from given text (comment or selftext) '''
		urls = []
		i = -1
		while True:
			i = text.find('://', i+1)
			if i == -1: break
			j = i
			while j < len(text) and text[j] not in [')', ']', ' ', '"', '\n', '\t']:
				j += 1
			urls.append('http%s' % text[i:j])
			i = j
		return list(set(urls)) # Kill duplicates

	@staticmethod
	def get_user_info(user):
		url = 'http://www.reddit.com/user/%s/about.json' % user
		try:
			Reddit.wait()
			r = Reddit.httpy.get(url)
			json = loads(str(r, 'utf-8'))
		except Exception as e:
			Reddit.debug('exception: %s' % str(e))
			raise e
		if not 'data' in json:
			Reddit.debug('data not found at %s, got: %s' % (url, r))
			raise Exception('data not found at %s' % url)
		data = json['data']
		user_info = User()
		user_info.name = data['name']
		user_info.created = int(data['created_utc'])
		user_info.comm_karma = data['comment_karma']
		user_info.link_karma = data['link_karma']
		return user_info

	''' Recursively print comments '''
	@staticmethod
	def print_comments(comments, depth=''):
		for i in xrange(0, len(comments)):
			comment = comments[i]
			print(depth + '  \\_ "%s" -/u/%s' % (comment.body.replace('\n', ' '), comment.author))
			if len(comment.comments) > 0:
				more = '   '
				if i < len(comments) - 1:
					more = ' | '
				Reddit.print_comments(comment.comments, depth=depth+more)

	# POST /api/friend
	# action	add
	# container	[my thing id, eg t2_6sxur]
	# type	friend
	# name	[friend_username]
	# id	#friend
	# uh	[userhash]
	# renderstyle	html

	@staticmethod
	def get_user_id(user=None):
		'''
			User = None means to get logged-on user's id
			Otherwise, look up ID of 'user'
		'''
		if user != None:
			# Requesting ID of another user
			r = "{no response}"
			try:
				Reddit.wait()
				r = Reddit.httpy.get('http://www.reddit.com/user/%s/about.json' % user)
				json = loads(str(r, 'utf-8'))
				if 'data' in json and 'id' in json['data']:
					return json['data']['id']
			except Exception as e:
				if '404' in str(e):
					Reddit.debug('user /u/%s is not found (404)' % user)
				raise e
			raise Exception('could not find user ID for %s at /u/%s/about.json: %s' % (user, r))

		# Requesting this user's ID
		if Reddit.user_id == None:
			Reddit.wait()
			r = Reddit.httpy.get('http://www.reddit.com/api/me.json')
			if 'data' in json and 'id' in json['data']:
				Reddit.user_id = 't2_%s' % json['data']['id']
			else:
				raise Exception('failed to get logged-in user\'s id from /api/me.json: %s' % r)
		return Reddit.user_id

	@staticmethod
	def add_friend(user):
		user_id = Reddit.get_user_id(user=None)
		d = {
				'action'   : 'add',
				'type'     : 'friend',
				'name'     : user,
				'container': user_id,
				'uh'       : Reddit.modhash,
				'id'       : '#friend',
				'renderstyle' : 'html'
			}
		Reddit.wait()
		r = Reddit.httpy.oldpost('http://www.reddit.com/api/friend' , d)
		if 'USER_DOESNT_EXIST' in r:
			Reddit.debug('USER_DOESNT_EXIST error while friending /u/%s' % user)
			raise Exception('USER_DOESNT_EXIST')

	@staticmethod
	def remove_friend(user):
		current_user_id = Reddit.get_user_id(user=None)
		friend_user_id  = Reddit.get_user_id(user=user)
		d = {
				'executed' : 'removed',
				'type'     : 'friend',
				'name'     : user,
				'container': current_user_id,
				'uh'       : Reddit.modhash,
				'id'       : friend_user_id,
				'renderstyle' : 'html'
			}
		Reddit.wait()
		r = Reddit.httpy.oldpost('http://www.reddit.com/api/unfriend' , d)
		if not r.strip() == '{}':
			Reddit.debug('did not receive expected response while unfriending /u/%s: %s' % (user, r))
			raise Exception('unexpected response while unfriending /u/%s: %s' % (user, r))

	@staticmethod
	def get_friends_list():
		Reddit.wait()
		r = Reddit.httpy.get('http://www.reddit.com/prefs/friends.json')
		json = loads(str(r, 'utf-8'))
		if len(json) == 0:
			raise Exception('no friends list found at /prefs/friends.json: %s' % r)

		json = json[0] # Assume first list returned is the 'friends' list

		if not 'data' in json or 'children' not in json['data']:
			raise Exception('no "data" and "children" found at /prefs/friends.json: %s' % r)
		friend_list = json['data']['children']
		return [x['name'] for x in friend_list]

if __name__ == '__main__':
    r = Reddit()
    r.login('testjswrapper', 'testjswrapper')
	#for child in Reddit.get_user('isisdisplaced', since='2st9x1'):
		#if type(child) == Post:
			#if child.selftext != None:
				#print('POST selftext:', Reddit.get_links_from_text(child.selftext), child.permalink()),
			#else:
				#print('POST url:', child.url, child.permalink())
		#elif type(child) == Comment:
			#print('COMMENT', child.body,)
		#print('created: %d' % child.created)

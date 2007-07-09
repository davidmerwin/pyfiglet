#!/usr/bin/env python

"""
Python FIGlet adaption
"""

import sys
from optparse import OptionParser
import os
import re
from zipfile import ZipFile

__version__ = '0.1'

__copyright__ = """
Copyright (C) 2007 Christopher Jones <cjones@insub.org>

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA
"""

class FigletError(Exception):
	def __init__(self, error):
		self.error = error

	def __str__(self):
		return self.error

class FontNotFound(FigletError):
	pass

class FontError(FigletError):
	pass


class FigletFont(object):
	def __init__(self, dir='.', font='standard'):
		self.dir = dir
		self.font = font

		self.comment = ''
		self.chars = {}
		self.width = {}
		self.data = None

		self.reMagicNumber = re.compile(r'^flf2.')
		self.reEndMarker = re.compile(r'(.)\s*$')

		self.readFontFile()
		self.loadFont()

	def readFontFile(self):
		fontPath = '%s/%s.flf' % (self.dir, self.font)
		if os.path.exists(fontPath) is False:
			raise FontNotFound, "%s doesn't exist" % fontPath

		try:
			fo = open(fontPath, 'rb')
		except Exception, e:
			raise FontError, "couldn't open %s: %s" % (fontPath, e)

		try: self.data = fo.read()
		finally: fo.close()


	def loadFont(self):
		try:
			"""
			Parse first line of file, the header
			"""
			data = self.data.splitlines()

			header = data.pop(0)
			if self.reMagicNumber.search(header) is None:
				raise FontError, '%s is not a valid figlet font' % fontPath

			header = self.reMagicNumber.sub('', header)
			header = header.split()
			
			if len(header) < 6:
				raise FontError, 'malformed header for %s' % fontPath

			hardBlank = header[0]
			height, baseLine, maxLength, oldLayout, commentLines = map(int, header[1:6])
			printDirection = fullLayout = codeTagCount = None

			# these are all optional for backwards compat
			if len(header) > 6: printDirection = int(header[6])
			if len(header) > 7: fullLayout = int(header[7])
			if len(header) > 8: codeTagCount = int(header[8])

			# useful for later
			self.height = height
			self.hardBlank = hardBlank
			self.printDirection = printDirection

			"""
			Strip out comment lines
			"""
			for i in range(0, commentLines):
				self.comment += data.pop(0)

			"""
			Load characters
			"""
			for i in range(32, 127):
				end = None
				width = 0
				for j in range(0, height):
					line = data.pop(0)
					if end is None:
						end = self.reEndMarker.search(line).group(1)

					line = line.replace(end, '')

					if len(line) > width:
						width = len(line)

					if self.chars.has_key(i) is False:
						self.chars[i] = []

					self.chars[i].append(line)

				self.width[i] = width


		except Exception, e:
			raise FontError, 'problem parsing %s font: %s' % (self.font, e)


	def __str__(self):
		return '<FigletFont object: %s>' % self.font



class ZippedFigletFont(FigletFont):
	def __init__(self, dir='.', font='standard', zipfile='fonts.zip'):
		self.zipfile = zipfile
		FigletFont.__init__(self, dir=dir, font=font)

	def readFontFile(self):
		if os.path.exists(self.zipfile) is False:
			raise FontNotFound, "%s doesn't exist" % self.zipfile

		fontPath = 'fonts/%s.flf' % self.font

		try:
			z = ZipFile(self.zipfile, 'r')
			files = z.namelist()
			if fontPath not in files:
				raise FontNotFound, '%s not found in %s' % (self.font, self.zipfile)

			self.data = z.read(fontPath)

		except Exception, e:
			raise FontError, "couldn't open %s: %s" % (fontPath, e)



"""
This class handles the dirty bits of kerning/smushing
"""
class FigletRenderingEngine(object):
	def __init__(self, base=None):
		self.base = base

		self.prevCharWidth = 100
		self.curCharWidth = 100
		self.smushMode = 0

		# constants
		self.SM_EQUAL = 1	# smush equal chars (not hardblanks)
		self.SM_LOWLINE = 2	# smush _ with any char in hierarchy
		self.SM_HIERARCHY = 4	# hierarchy: |, /\, [], {}, (), <>
		self.SM_PAIR = 8	# hierarchy: [ + ] -> |, { + } -> |, ( + ) -> |
		self.SM_BIGX = 16	# / + \ -> X, > + < -> X
		self.SM_HARDBLANK = 32	# hardblank + hardblank -> hardblank
		self.SM_KERN = 64
		self.SM_SMUSH = 128


	"""
	This is almost a direct translation from smushem() in
	FIGlet222. Could possibly be done more efficiently with
	Python idioms if anyone cares to undertake it. That wouldn't be I.
	"""
	def smushChars(self, left='', right=''):
		if left.isspace() is True: return right
		if right.isspace() is True: return left

		# Disallows overlapping if previous or current char has a width of 1 or zero
		if (self.prevCharWidth < 2) or (self.curCharWidth < 2): return

		# kerning only
		if (self.smushMode & self.SM_SMUSH) == 0: return

		# smushing by universal overlapping
		if (self.smushMode & 63) == 0:
			# Ensure preference to visiable characters.
			if left == self.base.Font.hardBlank: return right
			if right == self.base.Font.hardBlank: return left

			"""
			Ensures that the dominant (foreground)
			fig-character for overlapping is the latter in the
			user's text, not necessarily the rightmost character.
			"""
			if self.base.direction == 'right-to-left': return left
			else: return right

		if self.smushMode & self.SM_HARDBLANK:
			if left == self.base.Font.hardBlank and right == self.base.Font.hardBlank:
				return left

		if left == self.base.Font.hardBlank or right == self.base.Font.hardBlank:
			return

		if self.smushMode & self.SM_EQUAL:
			if left == right:
				return left

		if self.smushMode & self.SM_LOWLINE:
			if (left  == '_') and (right in r'|/\[]{}()<>'): return right
			if (right == '_') and (left  in r'|/\[]{}()<>'): return left

		if self.smushMode & self.SM_HIERARCHY:
			if (left  == '|')   and (right in r'|/\[]{}()<>'): return right
			if (right == '|')   and (left  in r'|/\[]{}()<>'): return left
			if (left  in r'\/') and (right in '[]{}()<>'): return right
			if (right in r'\/') and (left  in '[]{}()<>'): return left
			if (left  in '[]')  and (right in '{}()<>'): return right
			if (right in '[]')  and (left  in '{}()<>'): return left
			if (left  in '{}')  and (right in '()<>'): return right
			if (right in '{}')  and (left  in '()<>'): return left
			if (left  in '()')  and (right in '<>'): return right
			if (right in '()')  and (left  in '<>'): return left

		if self.smushMode & self.SM_PAIR:
			for pair in [left+right, right+left]:
				if pair in ['[]', '{}', '()']: return '|'

		if self.smushMode & self.SM_BIGX:
			if (left == '/') and (right == '\\'): return '|'
			if (right == '/') and (left == '\\'): return 'Y'
			if (left == '>') and (right == '<'): return 'X'

		return



	"""
	Render an ASCII text string in figlet
	"""
	def render(self, text):
		smushMode = 63
		curCharWidth = 0
		buffer = []

		for c in map(ord, list(text)):
			curChar = self.base.Font.chars[c]
			prevCharWidth = curCharWidth
			curCharWidth = self.base.Font.width[c]

			if len(buffer) == 0:
				buffer = curChar
				continue

			maxSmush = curCharWidth
			for row in range(0, self.base.Font.height):
				if self.base.direction == 'left-to-right':
					try:
						linebd = len(buffer[row].rstrip())
						ch1 = buffer[row][linebd-1]
					except:
						linebd = 0
						ch1 = ' '

					try:
						charbd = len(curChar[row]) - len(curChar[row].lstrip()) + 1
						ch2 = curChar[row][charbd-1]
					except:
						charbd = len(curChar[row])
						ch2 = ''

					amt = charbd + len(buffer[row])-1-linebd

					if ch1 == '' or ch1 == ' ':
						amt += 1
					elif ch2 != '':
						if self.smushChars(left=ch1, right=ch2) is not None:
							amt += 1

					if amt < maxSmush:
						maxSmush = amt

			for row in range(0, self.base.Font.height):
				for i in range(0, maxSmush):
					wBuffer = buffer[row]
					wChar = curChar[row]

					indA = len(wBuffer) - maxSmush + i
					left = wBuffer[indA]
					right = wChar[i]
					smushed = self.smushChars(left=left, right=right)

					if smushed is not None:
						l = list(wBuffer)
						l[len(l)-1] = smushed
						wBuffer = ''.join(l)

					
					wBuffer += wChar[maxSmush:]

					buffer[row] = wBuffer



		return '\n'.join(buffer)



"""
Main figlet class.
"""
class Figlet(object):
	def __init__(self, dir=None, zipfile=None, font='standard', direction='auto', justify='auto', width=80):
		self.dir = dir
		self.font = font
		self._direction = direction
		self._justify = justify
		self.width = width
		self.zipfile = zipfile
		self.setFont()
		self.engine = FigletRenderingEngine(base=self)


	def setFont(self, **kwargs):
		if kwargs.has_key('dir'):
			self.dir = kwargs['dir']

		if kwargs.has_key('font'):
			self.font = kwargs['font']

		if kwargs.has_key('zipfile'):
			self.zipfile = kwargs['zipfile']


		Font = None
		if self.zipfile is not None:
			try: Font = ZippedFigletFont(dir=self.dir, font=self.font, zipfile=self.zipfile)
			except: pass

		if Font is None and self.dir is not None:
			try: Font = FigletFont(dir=self.dir, font=self.font)
			except: pass

		if Font is None:
			raise FontNotFound, "Couldn't load font %s: Not found" % self.font

		self.Font = Font


	def getDirection(self):
		if self._direction == 'auto':
			direction = self.Font.printDirection
			if direction == 0:
				return 'left-to-right'
			elif direction == 1:
				return 'right-to-left'
		else:
			return self._direction

	direction = property(getDirection)

	def getJustify(self):
		if self._justify == 'auto':
			if self.direction == 'left-to-right':
				return 'left'
			elif self.direction == 'right-to-left':
				return 'right'

		else:
			return self._justify

	justify = property(getJustify)

	def renderText(self, text):
		return self.engine.render(text)





def main():
	dir = os.path.abspath(os.path.dirname(sys.argv[0]))

	parser = OptionParser(version=__version__, usage='%prog [options] text..')

	parser.add_option(	'-f', '--font', default='standard',
				help='font to render with (default: %default)', metavar='FONT' )

	parser.add_option(	'-d', '--fontdir', default=None,
				help='location of font files', metavar='DIR' )

	parser.add_option(	'-z', '--zipfile', default=dir+'/fonts.zip',
				help='specify a zipfile to use instead of a directory of fonts' )

	parser.add_option(	'-D', '--direction', type='choice', choices=('auto', 'left-to-right', 'right-to-left'),
				default='auto', metavar='DIRECTION',
				help='set direction text will be formatted in (default: %default)' )

	parser.add_option(	'-j', '--justify', type='choice', choices=('auto', 'left', 'center', 'right'),
				default='auto', metavar='SIDE',
				help='set justification, defaults to print direction' )

	parser.add_option(	'-w', '--width', type='int', default=80, metavar='COLS',
				help='set terminal width for wrapping/justification (default: %default)' )



	opts, args = parser.parse_args()

	if len(args) == 0:
		parser.print_help()
		return 1

	text = ' '.join(args)

	f = Figlet(
		dir=opts.fontdir, font=opts.font, direction=opts.direction,
		justify=opts.justify, width=opts.width, zipfile=opts.zipfile,
	)

	print f.renderText(text)


	return 0

if __name__ == '__main__': sys.exit(main())
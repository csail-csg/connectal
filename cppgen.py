##
## Copyright (C) 2013 Nokia, Inc
## Copyright (c) 2013-2014 Quanta Research Cambridge, Inc.

## Permission is hereby granted, free of charge, to any person
## obtaining a copy of this software and associated documentation
## files (the "Software"), to deal in the Software without
## restriction, including without limitation the rights to use, copy,
## modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is
## furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be
## included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
## EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
## MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
## NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
## BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
## ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
## CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.

import os
import syntax
import AST
import util
import functools
import math

proxyClassPrefixTemplate='''
class %(namespace)s%(className)s : public %(parentClass)s {
//proxyClass
    %(statusDecl)s
public:
    %(className)s(int id, PortalPoller *poller = 0);
'''
proxyClassSuffixTemplate='''
};
'''

wrapperClassPrefixTemplate='''
class %(namespace)s%(className)s : public %(parentClass)s {
//wrapperClass
public:
    %(className)s(PortalInternal *p, PortalPoller *poller = 0);
    %(className)s(int id, PortalPoller *poller = 0);
'''
wrapperClassSuffixTemplate='''
protected:
    virtual int handleMessage(unsigned int channel);
};
'''

proxyConstructorTemplate='''
%(namespace)s%(className)s::%(className)s(int id, PortalPoller *poller)
 : %(parentClass)s(id)
{
    %(statusInstantiate)s
}
'''

wrapperConstructorTemplate='''
%(namespace)s%(className)s::%(className)s(PortalInternal *p, PortalPoller *poller)
 : %(parentClass)s(p, poller)
{}
%(namespace)s%(className)s::%(className)s(int id, PortalPoller *poller)
 : %(parentClass)s(id, poller)
{}
'''

putFailedMethodName = "putFailed"

putFailedTemplate='''
void %(namespace)s%(className)s::%(putFailedMethodName)s(uint32_t v){
    const char* methodNameStrings[] = {%(putFailedStrings)s};
    fprintf(stderr, "putFailed: %%s\\n", methodNameStrings[v]);
    //exit(1);
  }
'''

responseSzCaseTemplate='''
    case %(channelNumber)s: 
    { 
        %(msg)s msg;
        for (int i = (msg.size()/4)-1; i >= 0; i--)
            buf[i] = READL(this, &map_base[PORTAL_IND_FIFO(%(channelNumber)s)]);
        msg.demarshall(buf);
        msg.indicate(this);
        break;
    }
'''

handleMessageTemplate='''
int %(namespace)s%(className)s::handleMessage(unsigned int channel)
{    
    unsigned int buf[1024];
    static int runaway = 0;
    
    switch (channel) {
%(responseSzCases)s
    default:
        printf("%(namespace)s%(className)s::handleMessage: unknown channel 0x%%x\\n", channel);
        if (runaway++ > 10) {
            printf("%(namespace)s%(className)s::handleMessage: too many bogus indications, exiting\\n");
            exit(-1);
        }
        return 0;
    }
    return 0;
}
'''

proxyMethodTemplate='''
void %(namespace)s%(className)s::%(methodName)s ( %(paramDeclarations)s )
{
    %(className)s%(methodName)sMSG msg;
    msg.channel = %(methodChannelOffset)s;
%(paramSetters)s
    sendMessage(&msg);
};
'''

msgTemplate='''
class %(className)s%(methodName)sMSG : public PortalMessage
{
public:
    struct {
%(paramStructDeclarations)s
    } payload;
    size_t size(){return %(payloadSize)s;}
    void marshall(unsigned int *buff) {
        int i = 0;
%(paramStructMarshall)s
    }
    void demarshall(unsigned int *buff){
        int i = 0;
%(paramStructDemarshall)s
    }
    void indicate(void *ind){ %(responseCase)s }
};
'''

def indent(f, indentation):
    for i in xrange(indentation):
        f.write(' ')

def capitalize(s):
    return '%s%s' % (s[0].upper(), s[1:])

class NoCMixin:
    def emitCDeclaration(self, f, indentation=0, namespace=''):
        pass
    def emitCImplementation(self, f):
        pass

class MethodMixin:
    def collectTypes(self):
        result = [self.return_type]
        result.append(AST.Type('Tuple', self.params))
        return result
    def resultTypeName(self):
        if (self.return_type):
            return self.return_type.cName()
        else:
            return int
    def formalParameters(self, params):
        return [ 'const %s%s %s' % (p.type.cName(), p.type.refParam(), p.name) for p in params]
    def emitCDeclaration(self, f, proxy, indentation=0, namespace=''):
        indent(f, indentation)
        resultTypeName = self.resultTypeName()
        if (not proxy):
            f.write('virtual ')
        f.write('void %s ( ' % cName(self.name))
        f.write(', '.join(self.formalParameters(self.params)))
        f.write(' )')
	# ugly hack
        if ((not proxy) and (not (self.name == putFailedMethodName))):
            f.write('= 0;\n')
        else:
            f.write(';\n')
    def emitCImplementation(self, f, className, namespace, proxy):

        # resurse interface types and flattening all structs into a list of types
        def collectMembers(scope, member):
            t = member.type
            tn = member.type.name
            if tn == 'Bit':
                return [('%s.%s'%(scope,member.name),t)]
            elif tn == 'Int' or tn == 'UInt':
                return [('%s.%s'%(scope,member.name),t)]
            elif tn == 'Float':
                return [('%s.%s'%(scope,member.name),t)]
            elif tn == 'Vector':
                return [('%s.%s'%(scope,member.name),t)]
            else:
                td = syntax.globalvars[tn]
                tdtype = td.tdtype
                if tdtype.type == 'Struct':
                    ns = '%s.%s' % (scope,member.name)
                    rv = map(functools.partial(collectMembers, ns), tdtype.elements)
                    return sum(rv,[])
                elif tdtype.type == 'Enum':
                    return [('%s.%s'%(scope,member.name),tdtype)]
                else:
                    return self.collectMembers(scope, tdtype.type)

        # pack flattened struct-member list into 32-bit wide bins.  If a type is wider than 32-bits or 
        # crosses a 32-bit boundary, it will appear in more than one bin (though with different ranges).  
        # This is intended to mimick exactly Bluespec struct packing.  The padding must match the code 
        # in Adapter.bsv.  the argument s is a list of bins, atoms is the flattened list, and pro represents
        # the number of bits already consumed from atoms[0].
        def accumWords(s, pro, atoms):
            if len(atoms) == 0:
                return [] if len(s) == 0 else [s]
            w = sum([x[1]-x[2] for x in s])
            a = atoms[0]
            aw = a[1].bitWidth();
            #print '%d %d %d' %(aw, pro, w)
            if (aw-pro+w == 32):
                ns = s+[(a[0],aw,pro,a[1],pro==0)]
                #print '%s (0)'% (a[0])
                return [ns]+accumWords([],0,atoms[1:])
            if (aw-pro+w < 32):
                ns = s+[(a[0],aw,pro,a[1],pro==0)]
                #print '%s (1)'% (a[0])
                return accumWords(ns,0,atoms[1:])
            else:
                ns = s+[(a[0],pro+(32-w),pro,a[1],pro==0)]
                #print '%s (2)'% (a[0])
                return [ns]+accumWords([],pro+(32-w), atoms)

        params = self.params
        paramDeclarations = self.formalParameters(params)
        paramStructDeclarations = [ '        %s %s%s;\n' % (p.type.cName(), p.name, p.type.bitSpec()) for p in params]
        
        argAtoms = sum(map(functools.partial(collectMembers, 'payload'), params), [])

        # for a in argAtoms:
        #     print a[0]
        # print ''

        argAtoms.reverse();
        argWords  = accumWords([], 0, argAtoms)

        # for a in argWords:
        #     for b in a:
        #         print '%s[%d:%d]' % (b[0], b[1], b[2])
        # print ''

        def marshall(w):
            off = 0
            word = []
            for e in w:
                field = e[0];
		if e[3].cName() == 'float':
		    return '        buff[i++] = *(int*)&%s;\n' % e[0];
                if e[2]:
                    field = '(%s>>%s)' % (field, e[2])
                if off:
                    field = '(%s<<%s)' % (field, off)
                if e[3].bitWidth() > 64:
                    field = '(const %s & std::bitset<%d>(0xFFFFFFFF)).to_ulong()' % (field, e[3].bitWidth())
                word.append(field)
                off = off+e[1]-e[2]
            return '        buff[i++] = %s;\n' % (''.join(util.intersperse('|', word)))

        def demarshall(w):
            off = 0
            word = []
            for e in w:
                # print e[0]+' (d)'
                ass = '=' if e[4] else '|='
                field = 'buff[i]'
		if e[3].cName() == 'float':
		    word.append('        %s = *(float*)&(%s);\n'%(e[0],field))
		    continue
                if off:
                    field = '%s>>%s' % (field, off)
                if e[3].bitWidth() < 32:
                    field = '((%s)&0x%xul)' % (field, ((1 << e[3].bitWidth())-1))
                if e[2]:
                    field = '((%s)(%s)<<%s)' % (e[3].cName(),field, e[2])
		word.append('        %s %s (%s)(%s);\n'%(e[0],ass,e[3].cName(),field))
                off = off+e[1]-e[2]
            word.append('        i++;\n');
            # print ''
            return ''.join(word)

        paramStructMarshall = map(marshall, argWords)
        paramStructDemarshall = map(demarshall, argWords)

        if not params:
            paramStructDeclarations = ['        int padding;\n']
        paramSetters = [ '    msg.payload.%s = %s;\n' % (p.name, p.name) for p in params]
        resultTypeName = self.resultTypeName()
        substs = {
            'namespace': namespace,
            'className': className,
            'methodName': cName(self.name),
            'MethodName': capitalize(cName(self.name)),
            'paramDeclarations': ', '.join(paramDeclarations),
            'paramStructDeclarations': ''.join(paramStructDeclarations),
            'paramStructMarshall': ''.join(paramStructMarshall),
            'paramStructDemarshall': ''.join(paramStructDemarshall),
            'paramSetters': ''.join(paramSetters),
            'paramNames': ', '.join(['msg->%s' % p.name for p in params]),
            'resultType': resultTypeName,
            'methodChannelOffset': 'CHAN_NUM_%s_%s' % (className, cName(self.name)),
            # if message is empty, we still send an int of padding
            'payloadSize' : max(4, 4*((sum([p.numBitsBSV() for p in self.params])+31)/32)) 
            }
        if (not proxy):
            substs['responseCase'] = ('((%(className)s *)ind)->%(name)s(%(params)s);\n'
                                      % { 'name': self.name,
                                          'className' : className,
                                          'params': ', '.join(['payload.%s' % (p.name) for p in self.params])})
            f.write(msgTemplate % substs)
        else:
            substs['responseCase'] = 'assert(false);'
            f.write(msgTemplate % substs)
            f.write(proxyMethodTemplate % substs)


class StructMemberMixin:
    def emitCDeclaration(self, f, indentation=0, namespace=''):
        indent(f, indentation)
        f.write('%s %s' % (self.type.cName(), self.name))
        if self.type.isBitField():
            f.write(' : %d' % self.type.bitWidth())
        f.write(';\n')

class TypeDefMixin:
    def emitCDeclaration(self,f,indentation=0, namespace=''):
        if self.tdtype.type == 'Struct' or self.tdtype.type == 'Enum':
            self.tdtype.emitCDeclaration(self.name,f,indentation,namespace)

class StructMixin:
    def collectTypes(self):
        result = [self]
        result.append(self.elements)
        return result
    def emitCDeclaration(self, name, f, indentation=0, namespace=''):
        indent(f, indentation)
        if (indentation == 0):
            f.write('typedef ')
        f.write('struct %s {\n' % name)
        for e in self.elements:
            e.emitCDeclaration(f, indentation+4)
        indent(f, indentation)
        f.write('}')
        if (indentation == 0):
            f.write(' %s;' % name)
        f.write('\n')
    def emitCImplementation(self, f, className='', namespace=''):
        pass

class EnumElementMixin:
    def cName(self):
        return self.name

class EnumMixin:
    def cName(self):
        return self.name
    def collectTypes(self):
        result = [self]
        return result
    def emitCDeclaration(self, name, f, indentation=0, namespace=''):
        indent(f, indentation)
        if (indentation == 0):
            f.write('typedef ')
        f.write('enum %s { ' % name)
        indent(f, indentation)
        f.write(', '.join(['%s_%s' % (name, e) for e in self.elements]))
        indent(f, indentation)
        f.write(' }')
        if (indentation == 0):
            f.write(' %s;' % name)
        f.write('\n')
    def emitCImplementation(self, f, className='', namespace=''):
        pass
    def bitWidth(self):
        return int(math.ceil(math.log(len(self.elements))))

class InterfaceMixin:
    def collectTypes(self):
        result = [d.collectTypes() for d in self.decls]
        return result
    def getSubinterface(self, name):
        subinterfaceName = name
        if not syntax.globalvars.has_key(subinterfaceName):
            return None
        subinterface = syntax.globalvars[subinterfaceName]
        #print 'subinterface', subinterface, subinterface
        return subinterface
    def insertPutFailedMethod(self):
        meth_name = putFailedMethodName
        meth_type = AST.Type("Action",[])
        meth_formal_params = [AST.Param("v", AST.Type("Bit",[AST.Type(32,[])]))]
        self.decls = self.decls + [AST.Method(meth_name, meth_type, meth_formal_params)]
    def assignRequestResponseChannels(self, channelNumber=0):
        for d in self.decls:
            if d.__class__ == AST.Method:
                d.channelNumber = channelNumber
                channelNumber = channelNumber + 1
        self.channelCount = channelNumber
    def parentClass(self, default):
        rv = default if (len(self.typeClassInstances)==0) else (self.typeClassInstances[0])
        return rv
    def hasPutFailed(self):
	rv = True in [d.name == putFailedMethodName for d in self.decls]
	return rv
    def global_name(self, s, suffix):
        return '%s%s_%s' % (cName(self.name), suffix, s)
    def emitCProxyDeclaration(self, f, of, suffix, indentation=0, namespace=''):
        className = "%s%s" % (cName(self.name), suffix)
        statusDecl = "%s%s *proxyStatus;" % (cName(self.name), 'ProxyStatus')
	reqChanNums = []
        for d in self.decls:
            reqChanNums.append('CHAN_NUM_%s' % self.global_name(d.name, suffix))
        subs = {'className': className,
                'namespace': namespace,
		'statusDecl' : '' if self.hasPutFailed() else statusDecl,
                'parentClass': self.parentClass('PortalInternal')}
        f.write(proxyClassPrefixTemplate % subs)
        for d in self.decls:
            d.emitCDeclaration(f, True, indentation + 4, namespace)
        f.write(proxyClassSuffixTemplate % subs)
	of.write('enum { ' + ','.join(reqChanNums) + '};\n')
    def emitCWrapperDeclaration(self, f, of, suffix, indentation=0, namespace=''):
        className = "%s%s" % (cName(self.name), suffix)
        indent(f, indentation)
	indChanNums = []
	for d in self.decls:
            indChanNums.append('CHAN_NUM_%s' % self.global_name(cName(d.name), suffix));
        subs = {'className': className,
                'namespace': namespace,
                'parentClass': self.parentClass('Portal')}
        f.write(wrapperClassPrefixTemplate % subs)
        for d in self.decls:
            d.emitCDeclaration(f, False, indentation + 4, namespace)
        f.write(wrapperClassSuffixTemplate % subs)
	of.write('enum { ' + ','.join(indChanNums) + '};\n')
    def emitCProxyImplementation(self, f,  suffix, namespace=''):
        className = "%s%s" % (cName(self.name), suffix)
	statusName = "%s%s" % (cName(self.name), 'ProxyStatus')
	statusInstantiate = '' if self.hasPutFailed() else 'proxyStatus = new %s(this, poller);\n' % statusName
        substitutions = {'namespace': namespace,
                         'className': className,
			 'statusInstantiate' : statusInstantiate,
                         'parentClass': self.parentClass('PortalInternal')}
        f.write(proxyConstructorTemplate % substitutions)
        for d in self.decls:
            d.emitCImplementation(f, className, namespace,True)
    def emitCWrapperImplementation (self, f,  suffix, namespace=''):
        className = "%s%s" % (cName(self.name), suffix)
        emitPutFailed = self.hasPutFailed()
        substitutions = {'namespace': namespace,
                         'className': className,
			 'putFailedMethodName' : putFailedMethodName,
                         'parentClass': self.parentClass('Portal'),
                         'responseSzCases': ''.join([responseSzCaseTemplate % { 'channelNumber': 'CHAN_NUM_%s' % self.global_name(cName(d.name), suffix),
                                                                                'msg': '%s%sMSG' % (className, d.name)}
                                                     for d in self.decls 
                                                     if d.type == 'Method' and d.return_type.name == 'Action']),
                         'putFailedStrings': '' if (not emitPutFailed) else ', '.join('"%s"' % (d.name) for d in self.req.decls if d.__class__ == AST.Method )}
        f.write(wrapperConstructorTemplate % substitutions)
        for d in self.decls:
            d.emitCImplementation(f, className, namespace, False);
        if emitPutFailed:
            f.write(putFailedTemplate % substitutions)
        f.write(handleMessageTemplate % substitutions)


class ParamMixin:
    def cName(self):
        return self.name
    def emitCDeclaration(self, f, indentation=0, namespace=''):
        indent(f, indentation)
        f.write('s %s' % (self.type, self.name))

class TypeMixin:
    def refParam(self):
        if (self.isBitField() and self.bitWidth() <= 64):
            return ''
        else:
            return '&'
    def cName(self):
        cid = self.name
        cid = cid.replace(' ', '')
        if cid == 'Bit':
            if self.params[0].numeric() <= 32:
                return 'uint32_t'
            elif self.params[0].numeric() <= 64:
                return 'uint64_t'
            else:
                return 'std::bitset<%d>' % (self.params[0].numeric())
        elif cid == 'Int':
            if self.params[0].numeric() == 32:
                return 'int'
            else:
                assert(False)
        elif cid == 'UInt':
            if self.params[0].numeric() == 32:
                return 'unsigned int'
            else:
                assert(False)
        elif cid == 'Float':
	    return 'float'
        elif cid == 'Vector':
            return 'bsvvector<%d,%s>' % (self.params[0].numeric(), self.params[1].cName())
        elif cid == 'Action':
            return 'int'
        elif cid == 'ActionValue':
            return self.params[0].cName()
        if self.params:
            name = '%sL_%s_P' % (cid, '_'.join([cName(t) for t in self.params if t]))
        else:
            name = cid
        return name
    def isBitField(self):
        return self.name == 'Bit' or self.name == 'Int' or self.name == 'UInt'
    def bitWidth(self):
        if self.name == 'Bit' or self.name == 'Int' or self.name == 'UInt':
            return int(self.params[0].name)
        if self.name == 'Float':
            return 32
        else:
            return 0
    def bitSpec(self):
        if self.isBitField():
            bw = self.bitWidth()
            if bw <= 64:
                return ':%d' % bw
            else:
                ## not compatible with use of std::bitset
                return ''
        return ''

def cName(x):
    if type(x) == str:
        x = x.replace(' ', '')
        x = x.replace('.', '$')
        return x
    else:
        return x.cName()

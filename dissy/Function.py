######################################################################
##
## Copyright (C) 2006,  Blekinge Institute of Technology
##
## Author:        Simon Kagstrom <simon.kagstrom@gmail.com>
## Description:   A function
##
## Licensed under the terms of GNU General Public License version 2
## (or later, at your option). See COPYING file distributed with Dissy
## for full text of the license.
##
######################################################################
import re, os, cgi

from dissy.Config import config
from dissy.Entity import Entity, AddressableEntity
from dissy.Instruction import Instruction
from dissy.JumpStreamHandler import *
from dissy.StrEntity import StrEntity

ADDRESS_REGEXP  = "[0-9,a-f,A-F]+"
ENCODING_REGEXP = ADDRESS_REGEXP + "[ ]"
INSN_REGEXP     = "[0-9,a-z,A-Z,_,\-,\.,\+]+"
INSN_ARGS_REGEXP= "\**[a-z,A-Z,0-9,_,\,,\(,\),\%,\$,\[,\],!,#,\-, ,&,{,},\*,\+\.]+"

insnRegExp = re.compile("[ ]*(" + ADDRESS_REGEXP + "):[ \t]+((?:" + ENCODING_REGEXP +")*)[ \t]+(" + INSN_REGEXP + ")+[ \t]*(" + INSN_ARGS_REGEXP + ")*")

class Function(AddressableEntity):
    def __init__(self, fileContainer, address, label, size=0):
        AddressableEntity.__init__(self, address = address, endAddress = address + size, baseAddress = fileContainer.baseAddress)
        self.label = label
        self.all = []
        self.insns = []
        self.addressToIns = {}
        self.file = fileContainer

    def addInstruction(self, insn):
        """Add an instruction to this function"""
        self.insns.append(insn)
        self.addressToIns[insn.address] = insn
        self.all.append(insn)
        if insn.address > self.endAddress:
            self.setSize(insn.address - self.address)

    def getFile(self):
        return self.file

    def addOther(self, other):
        self.all.append(StrEntity(self, other))

    def __getInstructionByOffset(self, insn, dir):
        idx = self.all.index(insn)
        return self.insns[ idx + dir ]

    def getPrevInstruction(self, insn):
        """Return the previous instruction from @a insn"""
        return self.__getInstructionByOffset(insn, -1)

    def getNextInstruction(self, insn):
        """Return the next instruction from @a insn"""
        return self.__getInstructionByOffset(insn, 1)

    def lookup(self, address):
        return self.addressToIns.get(address, None)

    def parse(self, try64bitWorkaround=False):
        """Parse the function."""
        count = 0
        start, end = self.getExtents()
        if try64bitWorkaround:
            if start & (1<<31):
                start = long(start) | 0xffffffff00000000
            if end & (1<<31):
                end = long(end) | 0xffffffff00000000

        lines = self.file.getFunctionObjdump(self.label, start, end)

        self.insns = []
        self.all = []
        firstNonEmpty=False
        for line in lines:
            # Weed away some unneeded stuff
            if line.startswith("Disassembly of section ") or line.startswith("%s: " % (self.file.filename)):
                continue
            if not firstNonEmpty and line.strip() == "":
                continue

            firstNonEmpty=True
            r = insnRegExp.match(line)
            if r != None:
                insn = Instruction(self, long("0x" + r.group(1),16), r.group(2), r.group(3), r.group(4))
                self.addInstruction(insn)
                count = count + 1
            else:
                self.addOther(cgi.escape(line))

        if count == 0 and try64bitWorkaround == False:
            # If we couldn't add anything interesting, try the 64-bit
            # workaround (for e.g., MIPS). See http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=369343
            return self.parse(try64bitWorkaround = True)

    def link(self):
        """
        Link the local jumps in this function. External jumps are
        linked to the function they reside in.
        """
        unresolved = []
        for insn in self.insns:
            if insn.hasLink() and not insn.link():
                unresolved.append(insn)

        positive, negative = self.getJumpDicts()

        # Fill in the jumps, forwards...
        self.fillInJumpStreams(positive, False)
        # ... and backwards
        self.all.reverse()
        self.fillInJumpStreams(negative, True)
        self.all.reverse()

        return unresolved

    def getInstructions(self):
        return self.insns

    def getAll(self):
        return self.all

    def getJumpDicts(self):
        """
        Get jump dictionaries for the forward and backward jumps.
        """
        positive = {}
        negative = {}
        for insn in self.insns:
            other = insn.getOutLink()
            if isinstance(other, Instruction) and other != insn:
                if other.address < insn.address:
                    # Jump from insn to other BACKWARDS
                    negative[insn.address] = (insn, other)
                else:
                    # Jump from insn to other FORWARDS
                    positive[insn.address] = (insn, other)
        return positive, negative

    def fillInJumpStreams(self, jumpDict, left):
        """
        Fill in the jump streams for a dictionary of start
        addresses. Specify if the left or right streams should be
        generated.
        """
        jumpStreamHandler = JumpStreamHandler()
        for insn in self.all:
            if isinstance(insn, Instruction):
                # Something starts on this address
                if jumpDict.has_key(insn.address):
                    stream = jumpStreamHandler.alloc()
                    if stream != None:
                        stream.start(jumpDict[insn.address] )
            jumpStreamHandler.update(insn)
            if left == True:
                insn.left_state = jumpStreamHandler.getStateTuple()
            else:
                insn.right_state = jumpStreamHandler.getStateTuple()


    def __str__(self):
        out = str("0x%08x" % self.address) + " " + str(self.label) + ":\n"
        for insn in self.insns:
            out = out + str(insn) + "\n"
        return out

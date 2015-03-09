// Copyright (c) 2013 Quanta Research Cambridge, Inc.

// Permission is hereby granted, free of charge, to any person
// obtaining a copy of this software and associated documentation
// files (the "Software"), to deal in the Software without
// restriction, including without limitation the rights to use, copy,
// modify, merge, publish, distribute, sublicense, and/or sell copies
// of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:

// The above copyright notice and this permission notice shall be
// included in all copies or substantial portions of the Software.

// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
// EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
// NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
// BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
// ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
// CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

import Vector::*;
import Portal::*;
import MemTypes::*;
import HostInterface::*;

typedef Empty TilePins;
typedef Empty ITilePins;
typedef 4 MaxTileMemClients;

interface TileSocket;
   interface PhysMemMaster#(PhysAddrWidth,DataBusWidth) portals;
   interface WriteOnly#(Bool) interrupt;
   interface Vector#(MaxTileMemClients, MemReadServer#(DataBusWidth)) readers;
   interface Vector#(MaxTileMemClients, MemWriteServer#(DataBusWidth)) writers;
   interface ITilePins pins;
endinterface

interface Tile;
   interface PhysMemSlave#(PhysAddrWidth,DataBusWidth) portals;
   interface ReadOnly#(Bool) interrupt;
   interface Vector#(MaxTileMemClients, MemReadClient#(DataBusWidth)) readers;
   interface Vector#(MaxTileMemClients, MemWriteClient#(DataBusWidth)) writers;
   interface TilePins pins;
endinterface

interface Framework#(numeric type numTiles);
   interface Vector#(numTiles, TileSocket) sockets;
endinterface


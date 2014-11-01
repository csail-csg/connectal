// bsv libraries
import SpecialFIFOs::*;
import Vector::*;
import StmtFSM::*;
import FIFO::*;

// portz libraries
import CtrlMux::*;
import Portal::*;
import Leds::*;
import ConnectalMemory::*;
import MemTypes::*;
import MemServer::*;
import MMU::*;

// generated by tool
import RegexpRequest::*;
import DmaDebugRequest::*;
import MMUConfigRequest::*;
import RegexpIndication::*;
import DmaDebugIndication::*;
import MMUConfigIndication::*;

// defined by user
import Regexp::*;

typedef enum {RegexpIndication, RegexpRequest, HostDmaDebugIndication, HostDmaDebugRequest, HostMMUConfigRequest, HostMMUConfigIndication} IfcNames deriving (Eq,Bits);

module mkConnectalTop(StdConnectalDmaTop#(PhysAddrWidth));

   RegexpIndicationProxy regexpIndicationProxy <- mkRegexpIndicationProxy(RegexpIndication);
   Regexp#(64) regexp <- mkRegexp(regexpIndicationProxy.ifc);
   RegexpRequestWrapper regexpRequestWrapper <- mkRegexpRequestWrapper(RegexpRequest,regexp.request);
   
   let readClients = cons(regexp.config_read_client, cons(regexp.haystack_read_client,nil));
   MMUConfigIndicationProxy hostMMUConfigIndicationProxy <- mkMMUConfigIndicationProxy(HostMMUConfigIndication);
   MMU#(PhysAddrWidth) hostMMU <- mkMMU(0, True, hostMMUConfigIndicationProxy.ifc);
   MMUConfigRequestWrapper hostMMUConfigRequestWrapper <- mkMMUConfigRequestWrapper(HostMMUConfigRequest, hostMMU.request);

   DmaDebugIndicationProxy hostDmaDebugIndicationProxy <- mkDmaDebugIndicationProxy(HostDmaDebugIndication);
   MemServer#(PhysAddrWidth,64,1) dma <- mkMemServerR(hostDmaDebugIndicationProxy.ifc, readClients, cons(hostMMU,nil));
   DmaDebugRequestWrapper hostDmaDebugRequestWrapper <- mkDmaDebugRequestWrapper(HostDmaDebugRequest, dma.request);

   Vector#(6,StdPortal) portals;
   portals[0] = regexpRequestWrapper.portalIfc;
   portals[1] = regexpIndicationProxy.portalIfc; 
   portals[2] = hostDmaDebugRequestWrapper.portalIfc;
   portals[3] = hostDmaDebugIndicationProxy.portalIfc; 
   portals[4] = hostMMUConfigRequestWrapper.portalIfc;
   portals[5] = hostMMUConfigIndicationProxy.portalIfc;
   let ctrl_mux <- mkSlaveMux(portals);
   
   interface interrupt = getInterruptVector(portals);
   interface slave = ctrl_mux;
   interface masters = dma.masters;
   interface leds = default_leds;
endmodule

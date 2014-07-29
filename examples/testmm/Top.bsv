// bsv libraries
import SpecialFIFOs::*;
import Vector::*;
import StmtFSM::*;
import FIFO::*;
import Connectable::*;

// portz libraries
import Directory::*;
import CtrlMux::*;
import Portal::*;
import Leds::*;
import PortalMemory::*;
import MemServer::*;
import PortalMemory::*;
import MemTypes::*;
import RbmTypes::*;
import HostInterface::*;

// generated by tool
import DmaConfigWrapper::*;
import DmaIndicationProxy::*;
import MmIndicationProxy::*;
import TimerIndicationProxy::*;
import TimerRequestWrapper::*;
import MmDebugRequestWrapper::*;
import MmDebugIndicationProxy::*;

`ifdef MATRIX_TN
import MmRequestTNWrapper::*;
import MatrixTN::*;
`else
`ifdef MATRIX_NT
import MmRequestNTWrapper::*;
import MatrixNT::*;
`endif
`endif

module  mkPortalTop#(HostType host)(PortalTop#(addrWidth,TMul#(32,N),Empty,NumberOfMasters))
   provisos (Add#(a__, addrWidth, 40),
	     Add#(a__, b__, 40),
	     Add#(addrWidth, c__, 52),
	     Add#(addrWidth, d__, 64),
	     Add#(e__, f__, 40),
	     Add#(f__, 12, b__),
	     Add#(b__, g__, 44)
	     );

   DmaIndicationProxy dmaIndicationProxy <- mkDmaIndicationProxy(DmaIndicationPortal);
   MmDebugIndicationProxy mmDebugIndicationProxy <- mkMmDebugIndicationProxy(MmDebugIndicationPortal);
   MmIndicationProxy mmIndicationProxy <- mkMmIndicationProxy(MmIndicationPortal);
   TimerIndicationProxy timerIndicationProxy <- mkTimerIndicationProxy(TimerIndicationPortal);
`ifdef MATRIX_TN
   MmTN#(N) mm <- mkMmTN(mmIndicationProxy.ifc, timerIndicationProxy.ifc, mmDebugIndicationProxy.ifc, host);
   MmRequestTNWrapper mmRequestWrapper <- mkMmRequestTNWrapper(MmRequestPortal,mm.mmRequest);
`else
`ifdef MATRIX_NT
   MmNT#(N) mm <- mkMmNT(mmIndicationProxy.ifc, timerIndicationProxy.ifc, mmDebugIndicationProxy.ifc, host);
   MmRequestNTWrapper mmRequestWrapper <- mkMmRequestNTWrapper(MmRequestPortal,mm.mmRequest);
`endif
`endif
   MmDebugRequestWrapper mmDebugRequestWrapper <- mkMmDebugRequestWrapper(MmDebugRequestPortal,mm.mmDebug);
   TimerRequestWrapper timerRequestWrapper <- mkTimerRequestWrapper(TimerRequestPortal,mm.timerRequest);
   
   Vector#(NumberOfMasters,ObjectReadClient#(TMul#(32,N)))  readClients  = mm.readClients;
   Vector#(NumberOfMasters,ObjectWriteClient#(TMul#(32,N))) writeClients = mm.writeClients;

   MemServer#(addrWidth, TMul#(32,N), NumberOfMasters) dma <- mkMemServer(dmaIndicationProxy.ifc, readClients, writeClients);
   DmaConfigWrapper dmaConfigWrapper <- mkDmaConfigWrapper(DmaConfigPortal,dma.request);

   Vector#(8,StdPortal) portals;
   portals[0] = mmRequestWrapper.portalIfc;
   portals[1] = mmIndicationProxy.portalIfc; 
   portals[2] = dmaConfigWrapper.portalIfc;
   portals[3] = dmaIndicationProxy.portalIfc; 
   portals[4] = timerRequestWrapper.portalIfc;
   portals[5] = timerIndicationProxy.portalIfc; 
   portals[6] = mmDebugIndicationProxy.portalIfc;
   portals[7] = mmDebugRequestWrapper.portalIfc;
   StdDirectory dir <- mkStdDirectory(portals);
   let ctrl_mux <- mkSlaveMux(dir,portals);
   
   interface interrupt = getInterruptVector(portals);
   interface slave = ctrl_mux;
   interface masters = dma.masters;

endmodule : mkPortalTop

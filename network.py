import random
import util

class Thing:
	i = 0
	def __init__(self):
		self.ID = Thing.i #Assign unique ID
		Thing.i += 1

class Device(Thing):
	def __init__(self):
		self.router = None
		self.throughput = 0
		#The following are for time_pass
		self.state = 0 #0 is free, 1 is busy
		self.bitsRemaining = 0
		self.packet = None
		self.connected = False
		self.completed = {}
		Thing.__init__(self)

	def connect(self, router, throughput):
		self.router = router
		self.throughput = throughput
		router.devices[self] = throughput
		self.connected = True

	def isConnected(self):
		return self.connected

	def getAdjacent(self):
		return {self.router: self.throughput}

	def timePass(self, time, destination, protocol=True): #takes in time and destination ID, True = Q-value, False = Dijikstra's
		if self.router and self.state == 0: #free and connected to internet
			if random.random() < 0.5: #with 50% probability, generate packet and send
				self.state = 1
				path = self.findPath(destination)[2:]
				self.packet = Packet(self.ID, destination.ID, random.randint(160,524280), path)
				# self.packet = Packet(self.ID, destination.ID, 160, path)
				self.bitsRemaining = self.packet.size

		if self.state == 1: #transmitting, subtracts from bits remaining
			self.bitsRemaining -= time * self.throughput
			#self.bitsRemaining = max(0, self.bitsRemaining)

			if self.bitsRemaining <= 0: #done transmitting
				self.state = 0 #become idle
				self.packet.delay += self.packet.size/self.throughput #add transmission time
				self.packet.path += [self.router.ID] #add router to path
				self.router.enqueue(self.packet) #pushed to router
				#print("Success")
				self.bitsRemaining = 0
				#print("dev state", self.ID, self.state, self.bitsRemaining)
				self.packet = None

	def findPath(self, dest):
		path = [dest.ID]
		prevNode = self.prev[dest]
		while prevNode[0] != None:
			path = [prevNode[0].ID] + path
			prevNode = self.prev[prevNode[0]]
		return path

	def dijikstra(self):
		closed = set()
		start = self
		fringe = util.PriorityQueue()
		fringe.push((start, 0), 0)
		self.prev = {start: (None, 0)}
		while not fringe.isEmpty():
			curr = fringe.pop()
			node = curr[0]
			cost = curr[1]
			closed.add(node.ID) #mark when dequeued, update avoids duplicates
			for nex, throughput in node.getAdjacent().items():
				loc = nex.ID
				if loc not in closed:
					netCost = cost + (1 / throughput)
					fringe.update((nex, netCost), netCost)
					if nex not in self.prev or netCost < self.prev[nex][1]:
						self.prev[nex] = (node, netCost)

	def poll(self): #return remaining time for event
		if self.bitsRemaining > 0 and self.throughput != 0: #how much time left to finish transmission
			return max(0.01, self.bitsRemaining / self.throughput)
		else: #don't pick this event as taking minimum time because there's nothing going on here
			return 1

	def receive(self, packet):
		src = packet.srcID
		if src in self.completed:
			self.completed[src].append([packet.size, packet.delay])
		else:
			self.completed[src] = [[packet.size, packet.delay]]

class Router(Thing):
	alpha = 0.8
	def __init__(self):
		self.linkList = {} #dictionary of neighboring routers and throughputs to them
		self.qValues = util.Counter()
		self.queue = util.Queue()
		self.devices = {}
		#The following are for time_pass
		self.state = 0 #0 is free, 1 is busy
		self.target = None
		self.minLink = None
		self.throughput = 0
		self.bitsRemaining = 0
		self.currentPacket = None
		Thing.__init__(self)

	def connect(self, router2, throughput): #Forms a link/edge between two routers by adding neighbor:throughput to both linkLists
		self.linkList[router2] = throughput
		router2.linkList[self] = throughput

	def getAdjacent(self):
		newDict = dict(self.linkList)
		newDict.update(self.devices)
		return newDict

	def getNeighbors(self, packet=None):
		if packet:
			neighbors = list(self.linkList.keys())
			for n in neighbors:
				if n.ID in packet.path:
					neighbors.remove(n)
			return neighbors
		else:
			return self.linkList.keys()

	def minQValue(self, dest): #used in updating Q-values
		neighbors = self.getNeighbors()
		return min([self.qValues[(dest, neighbor.ID)] for neighbor in neighbors])

	def qUpdate(self, nextLink, packet):
		nextQ = nextLink.minQValue(packet.destID) #gets t, the min Q-value from neighbor
		diff = (nextQ + packet.transmissionDelay + packet.qDelay) - self.qValues[(packet.destID, nextLink.ID)]
		self.qValues[(packet.destID,nextLink.ID)] += Router.alpha * diff

	def sendToDevice(self, packet):
		return packet.dest.receive(packet)

	def enqueue(self, packet):
		self.queue.push(packet)

	def isEmpty(self):
		return self.queue.isEmpty()

	def connected(self):
		return len(self.linkList.keys()) > 0

	def numConnects(self):
		return len(self.linkList.keys())

	def timePass(self, time, protocol=True):
		if self.state == 0 and not self.isEmpty(): #free and has packets
			#print("DEQUEUEING")
			self.currentPacket = self.queue.pop()
			if self.currentPacket: #packet actually exists and got dequeued
				#print("Got to router")
				self.state = 1 #busy
				self.bitsRemaining = self.currentPacket.size
				dest = self.currentPacket.destID
				#print("dest", dest)

				for device,throughput in self.devices.items(): 
					if device.ID == dest: #if the destination device is connected to router
						self.target = device
						self.throughput = throughput

				if self.target == None: #if we have to forward to a different router
					if protocol == False:
						nextID = self.currentPacket.dPath[0]
						for link in self.linkList:
							if link.ID == nextID:
								self.target = link
								self.throughput = self.linkList[link]
								break
						del self.currentPacket.dPath[0]
					else:
						minQ = 1e100
						self.minLink = None
						#finds minimum Q-value neighbor that the packet has not already visited
						for neighbor in self.getNeighbors(self.currentPacket): 
							nextQ = self.qValues[(dest, neighbor.ID)]
							if nextQ <= minQ:
								minQ = nextQ
								self.minLink = neighbor
						if self.minLink != None: #set up to transmit to neighboring router
							#print("transmitting")
							self.target = self.minLink
							self.throughput = self.linkList[self.minLink]
						else: #no neighbors, reset state and discard packet
							self.state = 0
							self.packet = None
							self.bitsRemaining = 0

		if self.state == 1: #transmitting
			#print("before", self.bitsRemaining, time)
			self.bitsRemaining -= time * self.throughput #actually transmit
			#print("after", self.bitsRemaining)
			#self.bitsRemaining = max(0, self.bitsRemaining)
			
			if self.bitsRemaining <= 0: #done transmitting, reset everything
				#print("forwarding")
				self.state = 0

				transmissionTime = self.currentPacket.size/self.throughput
				self.currentPacket.delay += transmissionTime #add transmission time
				self.currentPacket.transmissionDelay += transmissionTime
				self.queue.updateAll(transmissionTime)

				self.currentPacket.path += [self.target]
				if isinstance(self.target, Router):
					self.qUpdate(self.target, self.currentPacket) #updates Q value based on the neighbor
					self.currentPacket.transmissionDelay = 0
					self.currentPacket.qDelay = 0
					self.target.enqueue(self.currentPacket) #puts packet in next router's queue
					self.currentPacket.qPath.append(self.target.ID)
				else: #target is a device/destination
					#print("made it!!!")
					self.currentPacket.qPath.append(self.target.ID)
					if (self.currentPacket.srcID == 12 or self.currentPacket.srcID == 15) and protocol:
						print("qPath from", self.currentPacket.srcID, "to", self.currentPacket.destID, "is", self.currentPacket.qPath)
					self.target.receive(self.currentPacket)
				self.target = None
				self.throughput = 0
				self.bitsRemaining = 0
				self.currentPacket = None

	def poll(self): #return remaining time for event
		if self.bitsRemaining > 0 and self.throughput != 0: #how much time left to finish transmission
			return max(1, self.bitsRemaining / self.throughput)
		else: #don't pick this event as taking minimum time because there's nothing going on here
			return 1

class Packet:
	def __init__(self, source, destination, size, pathToTake = []):
		if source == 12 or source == 15:
			print("dPath from", source, "to", destination, "is", pathToTake)
		self.srcID = source
		self.destID = destination
		self.size = size
		self.delay = 0 #lifetime delay
		self.path = [source] #Path in Q-values...
		self.qDelay = 0 #Delay from queue
		self.transmissionDelay = 0 #Delay with transmission
		self.dPath = pathToTake #Dijikstra's path
		self.qPath = [source]
		
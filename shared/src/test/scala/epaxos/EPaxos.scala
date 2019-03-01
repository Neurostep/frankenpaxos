package epaxos

import frankenpaxos.simulator._
import frankenpaxos.epaxos._
import org.scalacheck
import org.scalacheck.Gen
import org.scalacheck.rng.Seed
import scala.collection.mutable

class EPaxos(val f: Int) {
  val logger = new FakeLogger()
  val transport = new FakeTransport(logger)
  val numClients = f + 1
  val numReplicas = 2 * (f + 1)

  // Configuration.
  val config = Config[FakeTransport](
    f = f,
    replicaAddresses = for (i <- 1 to numReplicas)
      yield FakeTransportAddress(s"Replica $i"),
  )

  // Clients.
  val clients = for (i <- 1 to numClients)
    yield
      new Client[FakeTransport](
        FakeTransportAddress(s"Client $i"),
        transport,
        logger,
        config
      )

  // Replicas
  val replicas = for (i <- 1 to numReplicas)
    yield
      new Replica[FakeTransport](
        FakeTransportAddress(s"Replica $i"),
        transport,
        logger,
        config
      )
}

sealed trait EPaxosCommand
case class Propose(clientIndex: Int, value: String) extends EPaxosCommand
case class TransportCommand(command: FakeTransport.Command)
    extends EPaxosCommand

class SimulatedEPaxos(val f: Int)
    extends SimulatedSystem[SimulatedEPaxos] {
  override type System = (EPaxos, Set[String])
  override type State = Set[String]
  override type Command = EPaxosCommand

  val commands: mutable.ListBuffer[String] = mutable.ListBuffer()

  def chosenValues(ePaxos: EPaxos): Set[String] = {
    // First, we look at any chosen values that the clients and proposers have
    // learned.
    //val clientChosen = paxos.clients.flatMap(_.chosenValue).to[Set]
    //val proposerChosen = paxos.proposers.flatMap(_.chosenValue).to[Set]

    // Next, we compute any value chosen by the acceptors. A value is
    // considered chosen if it has a majority of votes in the same round.
    //val votes: Seq[(Int, String)] = paxos.acceptors.flatMap(acceptor => {
    //  acceptor.voteValue.map((acceptor.voteRound, _))
    //})
    //val acceptorChosen: Set[String] =
    //  votes
    //    .filter(round_and_value => {
    //      votes.count(_ == round_and_value) >= f + 1
    //    })
    //    .map(_._2)
    //    .to[Set]

    //clientChosen ++ proposerChosen ++ acceptorChosen
    var commands: mutable.Set[String] = mutable.Set()
    for (client <- ePaxos.clients) {
      commands = commands.union(client.replies)
    }
    commands.toSet
  }

  override def newSystem(): SimulatedEPaxos#System = {
    (new EPaxos(f), Set())
  }

  override def getState(
      system: SimulatedEPaxos#System
  ): SimulatedEPaxos#State = {
    system._2
  }

  override def invariantHolds(
      newState: SimulatedEPaxos#State,
      oldState: Option[SimulatedEPaxos#State]
  ): Option[String] = {
    /*if (newState.size > 1) {
      return Some(
        s"Multiple values have been chosen: $newState (previously $oldState)."
      )
    }*/

    if (oldState.isDefined && !oldState.get.subsetOf(newState)) {
      return Some(
        s"Different values have been chosen: ${oldState.get} and " +
          s"then $newState."
      )
    }

    val instanceCommandMapping: mutable.Map[String, Int] = mutable.Map()
    for (state <- newState) {
      val tokens: Array[String] = state.split(": ")
      instanceCommandMapping.put(tokens(0), instanceCommandMapping.getOrElse(tokens(0), 0) + 1)
    }

    for (key <- instanceCommandMapping.keys) {
      if (instanceCommandMapping.getOrElse(key, 0) > 1) {
        return Some("More than one value has been chosen for a single instance")
      }
    }

    None
  }

  override def generateCommand(
      system: SimulatedEPaxos#System
  ): Option[SimulatedEPaxos#Command] = {
    val (ePaxos, _) = system

    var subgens = mutable.Buffer[(Int, Gen[SimulatedEPaxos#Command])]()
    subgens += (
      (
        ePaxos.numClients,
        for (clientId <- Gen.choose(0, ePaxos.numClients - 1);
             value <- Gen.listOfN(10, Gen.alphaLowerChar).map(_.mkString("")))
          yield Propose(clientId, value)
      )
    )

    if ((ePaxos.transport.messages.size +
          ePaxos.transport.runningTimers().size) > 0) {
      subgens += (
        (
          ePaxos.transport.messages.size +
            ePaxos.transport.runningTimers().size,
          FakeTransport
            .generateCommand(ePaxos.transport)
            .map(TransportCommand(_))
        )
      )
    }

    val gen: Gen[SimulatedEPaxos#Command] = Gen.frequency(subgens: _*)
    gen.apply(Gen.Parameters.default, Seed.random())
  }

  override def runCommand(
      system: SimulatedEPaxos#System,
      command: SimulatedEPaxos#Command
  ): SimulatedEPaxos#System = {
    val (ePaxos, allChosenValues) = system
    command match {
      case Propose(clientId, value) =>
        //println("Propose to client: " + clientId + " with value " + value)
        commands.append(value)
        val r = scala.util.Random
        val index: Int = r.nextInt(commands.size)

        val one: CommandPair = CommandPair(commands(index), value)
        val two: CommandPair = CommandPair(value, commands(index))

        for (rep <- ePaxos.replicas) {
          rep.interferenceData.put(one, true)
          rep.interferenceData.put(two, true)
        }

        ePaxos.clients(clientId).propose(value)
      case TransportCommand(command) =>
        FakeTransport.runCommand(ePaxos.transport, command)
    }
    (ePaxos, allChosenValues ++ chosenValues(ePaxos))
  }
}

package frankenpaxos.sum

import frankenpaxos.Actor
import frankenpaxos.Logger
import frankenpaxos.ProtoSerializer
import frankenpaxos.Chan
import scala.scalajs.js.annotation._

@JSExportAll
object ClientInboundSerializer extends ProtoSerializer[ClientInbound] {
  type A = ClientInbound
  override def toBytes(x: A): Array[Byte] = super.toBytes(x)
  override def fromBytes(bytes: Array[Byte]): A = super.fromBytes(bytes)
  override def toPrettyString(x: A): String = super.toPrettyString(x)
}

@JSExportAll
object Client {
  val serializer = ClientInboundSerializer
}

@JSExportAll
class Client[Transport <: frankenpaxos.Transport[Transport]](
    srcAddress: Transport#Address,
    dstAddress: Transport#Address,
    transport: Transport,
    logger: Logger
) extends Actor(srcAddress, transport, logger) {
  override type InboundMessage = ClientInbound
  override def serializer = Client.serializer

  private val server =
    chan[Server[Transport]](dstAddress, Server.serializer)

  private val pingTimer: Transport#Timer =
    timer("pingTimer", java.time.Duration.ofSeconds(1), () => {
      addImpl(1)
      pingTimer.start()
    });
  pingTimer.start();

  var numMessagesReceived: Int = 0

  logger.info(s"Sum client listening on $srcAddress.")

  override def receive(src: Transport#Address, reply: InboundMessage): Unit = {
    numMessagesReceived += 1
    logger.info(s"Received ${reply.sum} from $src.")
  }

  private def addImpl(x: Int): Unit = {
    server.send(ServerInbound(x = x))
  }

  def add(x: Int): Unit = {
    transport.executionContext().execute(() => addImpl(x))
  }
}

package frankenpaxos.sum

import frankenpaxos.Actor
import frankenpaxos.Logger
import frankenpaxos.ProtoSerializer
import frankenpaxos.monitoring.Collectors
import frankenpaxos.monitoring.Counter
import frankenpaxos.monitoring.PrometheusCollectors
import java.net.InetAddress
import java.net.InetSocketAddress
import scala.scalajs.js.annotation._

@JSExportAll
object ServerInboundSerializer extends ProtoSerializer[ServerInbound] {
  type A = ServerInbound
  override def toBytes(x: A): Array[Byte] = super.toBytes(x)
  override def fromBytes(bytes: Array[Byte]): A = super.fromBytes(bytes)
  override def toPrettyString(x: A): String = super.toPrettyString(x)
}

object Server {
  val serializer = ServerInboundSerializer
}

class ServerMetrics(collectors: Collectors) {
  val sumRequestsTotal: Counter = collectors.counter
    .build()
    .name("echo_requests_total")
    .help("Total sum requests.")
    .register()
}

@JSExportAll
class Server[Transport <: frankenpaxos.Transport[Transport]](
    address: Transport#Address,
    transport: Transport,
    logger: Logger,
    metrics: ServerMetrics = new ServerMetrics(PrometheusCollectors)
) extends Actor(address, transport, logger) {
  override type InboundMessage = ServerInbound
  override def serializer = Server.serializer

  var runningSum: Int = 0

  logger.info(s"Sum server listening on $address.")

  override def receive(src: Transport#Address, request: ServerInbound): Unit = {
    logger.debug(s"Received ${request.x} from $src.")
    runningSum += request.x
    metrics.sumRequestsTotal.inc()

    val client = chan[Client[Transport]](src, Client.serializer)
    client.send(ClientInbound(sum = runningSum))
  }
}

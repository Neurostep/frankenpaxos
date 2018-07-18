package zeno

trait Transport[Self <: Transport[Self]] {
  type Address <: zeno.Address
  type Timer <: zeno.Timer

  def register(address: Self#Address, actor: Actor[Self]): Unit
  def send(src: Self#Address, dst: Self#Address, bytes: Array[Byte]): Unit
  def timer(
      name: String,
      delay: java.time.Duration,
      f: () => Unit
  ): Self#Timer
}

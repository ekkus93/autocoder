#[path = "src/lib.rs"] mod candidate;
fn main() {
  let args: Vec<String> = std::env::args().collect();
  let value = candidate::ceil_div(args[1].parse::<u64>().unwrap(), args[2].parse::<u64>().unwrap());
  println!("{{\"value\":{}}}", &value.to_string());
}

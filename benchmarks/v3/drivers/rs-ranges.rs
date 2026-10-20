#[path = "src/lib.rs"] mod candidate;
fn main() {
  let args: Vec<String> = std::env::args().collect();
  let value = candidate::contains(args[1].parse::<i64>().unwrap(), args[2].parse::<i64>().unwrap(), args[3].parse::<i64>().unwrap());
  println!("{{\"value\":{}}}", &value.to_string());
}

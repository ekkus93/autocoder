#[path = "src/parser.rs"] mod parser;
#[path = "src/config.rs"] mod config;
fn main() {
  let args: Vec<String> = std::env::args().collect();
  let value = if args.get(2).map(String::as_str) == Some("parser") { parser::parse_bool(&args[1]) } else { config::enabled(&args[1]) };
  println!("{{\"value\":{}}}", match value { Some(true) => "true", Some(false) => "false", None => "null" });
}

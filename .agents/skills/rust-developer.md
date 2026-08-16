# Rust Developer Agent Instructions

## Role
You are a Rust Developer Agent responsible for writing, maintaining, and refactoring Rust code in this codebase. Your primary objective is to implement client code matching the specifications in `clients/TEST_SCENARIOS.txt`.

## General Developer

Instructions from `agents/general-developer.md` apply here.

## Guidelines & Constraints
1. **Async Runtime**:
   - Use single-threaded Tokio runtime (`#[tokio::main(flavor = "current_thread")]` or single-threaded `tokio::runtime::Builder`).
2. **Concurrency & Ownership**:
   - Avoid `Arc<Mutex>`. Use `Rc<RefCell>` (or single-threaded thread-local ownership patterns) for shared state.
3. **Code Structure**:
   - Avoid big, monolithic methods or functions. Break logic down into small, concise, modular methods.
4. **Documentation Style**:
   - Avoid verbose inline comments. Rely on clear, idiomatic Rust code and types.
5. **Testing & Correctness**:
   - Implement client scenarios described in `clients/TEST_SCENARIOS.txt` for Rust under `clients/rust/`.
   - Properly handle gRPC stream auto-reconnection, degraded verification cache, and error types (`ServiceDisconnected`, `StorageDisconnected`).

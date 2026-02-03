import pyhop
import json

# 1. THE GATEKEEPERS
def check_enough(state, ID, item, num):
    # If the state already has the item, return success (empty list) instantly.
    if getattr(state, item)[ID] >= num:
        return []
    return False

def produce_enough(state, ID, item, num):
    # Use an intermediate task to break the cycle
    return [('execute_production', ID, item, num)]

# 2. THE PRODUCTION BRIDGE (breaks cycles)
def execute_production(state, ID, item, num):
    # This task is only called if we don't have enough.
    # It calls 'produce', then RE-VERIFIES the state.
    return [('produce', ID, item), ('have_enough', ID, item, num)]

pyhop.declare_methods('have_enough', check_enough, produce_enough)
pyhop.declare_methods('execute_production', execute_production)

def produce(state, ID, item):
    return [('produce_{}'.format(item), ID)]

pyhop.declare_methods('produce', produce)

def make_method(name, rule):
    def method(state, ID):
        # If this recipe produces a tool we already have, we're done!
        for item in rule['Produces']:
            if item in ['bench', 'furnace', 'iron_pickaxe', 'stone_pickaxe', 'wooden_pickaxe']:
                if getattr(state, item)[ID] > 0:
                    return []  # Success - we already have it, no work needed
        
        # Build subtasks list
        subtasks = []
        
        # First, ensure we have required tools (but don't consume them)
        if 'Requires' in rule:
            for item, num in rule['Requires'].items():
                subtasks.append(('have_enough', ID, item, num))
        
        # Then, ensure we have consumable items
        if 'Consumes' in rule:
            for item, num in rule['Consumes'].items():
                subtasks.append(('have_enough', ID, item, num))
        
        # Finally, execute the operation
        op_name = 'op_' + name.replace(' ', '_')
        subtasks.append((op_name, ID))
        
        return subtasks
    return method

def declare_methods(data):
    # Map each producible item to all recipes that can produce it
    production_map = {}
    for name, rule in data['Recipes'].items():
        for item in rule['Produces']:
            if item not in production_map:
                production_map[item] = []
            production_map[item].append((name, rule))

    # For each item, declare methods in order of efficiency (by time)
    for item, recipes in production_map.items():
        # Sort by time - faster recipes first
        recipes.sort(key=lambda x: x[1]['Time'])
        
        methods_to_declare = []
        for name, rule in recipes:
            m_func = make_method(name, rule)
            m_func.__name__ = 'produce_method_' + name.replace(' ', '_')
            methods_to_declare.append(m_func)
        
        pyhop.declare_methods('produce_' + item, *methods_to_declare)

def make_operator(rule):
    def operator(state, ID):
        # Check if we have enough time
        if state.time[ID] < rule['Time']:
            return False
        
        # Check if we have required tools
        if 'Requires' in rule:
            for item, num in rule['Requires'].items():
                if getattr(state, item)[ID] < num:
                    return False
        
        # Check if we have consumable items
        if 'Consumes' in rule:
            for item, num in rule['Consumes'].items():
                if getattr(state, item)[ID] < num:
                    return False
        
        # Consume items
        if 'Consumes' in rule:
            for item, num in rule['Consumes'].items():
                getattr(state, item)[ID] -= num
        
        # Produce items
        for item, num in rule['Produces'].items():
            getattr(state, item)[ID] += num
        
        # Consume time
        state.time[ID] -= rule['Time']
        
        return state
    return operator

def declare_operators(data):
    operator_list = []
    for name, rule in data['Recipes'].items():
        op_func = make_operator(rule)
        op_func.__name__ = 'op_' + name.replace(' ', '_')
        operator_list.append(op_func)
    pyhop.declare_operators(*operator_list)

def add_heuristic(data, ID):
    def heuristic(state, curr_task, tasks, plan, depth, calling_stack):
        # Prune if we're out of time
        if state.time[ID] < 0:
            return True
        
        # Prevent infinite depth
        if depth > 400:
            return True
        
        # Smart cycle detection for have_enough and execute_production
        if curr_task[0] in ['have_enough', 'execute_production'] and curr_task in calling_stack:
            if len(curr_task) == 4:
                item = curr_task[2]
                num_needed = curr_task[3]
                current_amount = getattr(state, item)[ID]
                
                # If we have enough now, definitely not a cycle
                if current_amount >= num_needed:
                    return False
                
                # Count repetitions of this exact task
                count = calling_stack.count(curr_task)
                
                # Allow repetitions proportional to quantity needed
                # Multiplier of 3 accounts for: trying different recipes, backtracking, setup
                # For small quantities (1-3), allow at least 10 attempts
                max_allowed = max(num_needed * 3, 10)
                
                if count > max_allowed:
                    return True
        
        return False
    
    pyhop.add_check(heuristic)

def define_ordering(data, ID):
    def reorder_methods(state, curr_task, tasks, plan, depth, calling_stack, methods):
        if not methods or len(methods) <= 1:
            return methods
        
        # Prioritize methods where we already have the prerequisites
        ready = []
        not_ready = []
        
        for method in methods:
            subtasks = pyhop.get_subtasks(method, state, curr_task)
            if subtasks is False:
                continue
            
            # Check if we're ready to execute this method
            is_ready = True
            for subtask in subtasks:
                if subtask[0] == 'have_enough' and len(subtask) == 4:
                    item = subtask[2]
                    num = subtask[3]
                    if getattr(state, item)[ID] < num:
                        is_ready = False
                        break
            
            if is_ready:
                ready.append(method)
            else:
                not_ready.append(method)
        
        # Try ready methods first, then not ready
        return ready + not_ready
    
    pyhop.define_ordering(reorder_methods)

def set_up_state(data, ID):
    state = pyhop.State('state')
    state.time = {ID: data['Problem']['Time']}
    
    # Initialize all items and tools to 0
    all_items = set(data['Items']) | set(data['Tools'])
    for item in all_items:
        setattr(state, item, {ID: 0})
    
    # Set initial state
    for item, num in data['Problem']['Initial'].items():
        getattr(state, item)[ID] = num
    
    return state

def set_up_goals(data, ID):
    goals = []
    for item, num in data['Problem']['Goal'].items():
        goals.append(('have_enough', ID, item, num))
    return goals

if __name__ == '__main__':
    import sys
    rules_filename = 'crafting.json'
    
    if len(sys.argv) > 1:
        rules_filename = sys.argv[1]
    
    with open(rules_filename) as f:
        data = json.load(f)
    
    agent_id = 'agent'
    state = set_up_state(data, agent_id)
    goals = set_up_goals(data, agent_id)
    
    declare_operators(data)
    declare_methods(data)
    add_heuristic(data, agent_id)
    define_ordering(data, agent_id)
    
    result = pyhop.pyhop(state, goals, verbose=1)
    
    if result:
        print("\nPlan found!")
        print("Steps:", len(result))
        for i, step in enumerate(result):
            print(f"{i+1}. {step}")
    else:
        print("\nNo plan found!")

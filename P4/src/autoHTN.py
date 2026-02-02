import pyhop
import json

def check_enough(state, ID, item, num):
	if getattr(state,item)[ID] >= num: return []
	return False

def produce_enough(state, ID, item, num):
	return [('produce', ID, item), ('have_enough', ID, item, num)]

pyhop.declare_methods('have_enough', check_enough, produce_enough)

def produce(state, ID, item):
	return [('produce_{}'.format(item), ID)]

pyhop.declare_methods('produce', produce)

def make_method(name, rule):
	def method(state, ID):
		subtasks = []
		# Logic: If the recipe has 'Requires' (tools), we must ensure they are in hand first
		if 'Requires' in rule:
			for item, num in rule['Requires'].items():
				subtasks.append(('have_enough', ID, item, num))
		
		# Logic: Ensure all 'Consumes' ingredients are available
		if 'Consumes' in rule:
			for item, num in rule['Consumes'].items():
				subtasks.append(('have_enough', ID, item, num))
		
		# After requirements are met, add the primitive operator to the task list
		op_name = 'op_' + name.replace(' ', '_')
		subtasks.append((op_name, ID))
		return subtasks
	return method

def declare_methods(data):
	# Map each item to the various recipes that can produce it
	production_map = {}
	for name, rule in data['Recipes'].items():
		for item in rule['Produces']:
			if item not in production_map:
				production_map[item] = []
			production_map[item].append((name, rule))

	for item, recipes in production_map.items():
		# Sort recipes by Time cost so the planner prioritizes the most efficient path
		recipes.sort(key=lambda x: x[1]['Time'])
		
		methods_to_declare = []
		for name, rule in recipes:
			m_func = make_method(name, rule)
			# Name methods with 'produce_' prefix per project requirements
			m_func.__name__ = 'produce_' + name.replace(' ', '_')
			methods_to_declare.append(m_func)
		
		# Register alternate methods for the specific production task
		pyhop.declare_methods('produce_' + item, *methods_to_declare)

def make_operator(rule):
	def operator(state, ID):
		# Primitive check: Ensure agent has enough time for the action
		if state.time[ID] < rule['Time']:
			return False
		
		# Condition check: Verify Required tools are present
		if 'Requires' in rule:
			for item, num in rule['Requires'].items():
				if getattr(state, item)[ID] < num:
					return False
		
		# Condition check: Verify and deduct Consumed items
		if 'Consumes' in rule:
			for item, num in rule['Consumes'].items():
				if getattr(state, item)[ID] < num:
					return False
			for item, num in rule['Consumes'].items():
				getattr(state, item)[ID] -= num

		# Execution: Update state with produced items
		for item, num in rule['Produces'].items():
			getattr(state, item)[ID] += num
			
		# Execution: Deduct time cost
		state.time[ID] -= rule['Time']
		return state
	return operator

def declare_operators(data):
	operator_list = []
	for name, rule in data['Recipes'].items():
		op_func = make_operator(rule)
		# Name operators with 'op_' prefix per project requirements
		op_func.__name__ = 'op_' + name.replace(' ', '_')
		operator_list.append(op_func)
	
	# Register all primitive actions to Pyhop
	pyhop.declare_operators(*operator_list)

def add_heuristic(data, ID):
    def heuristic(state, curr_task, tasks, plan, depth, calling_stack):
        # Prune if time is exceeded
        if state.time[ID] < 0:
            return True
        
        task_name = curr_task[0]
        
        # Cycle Prevention: Strict pruning for production tasks
        if task_name.startswith('produce_'):
            if calling_stack.count(curr_task) > 1:
                return True
        
        # Accumulation Permission: Relaxed limit for 'have_enough'
        elif calling_stack.count(curr_task) > 50:
            return True
            
        return False
    pyhop.add_check(heuristic)

def define_ordering(data, ID):
    def reorder_methods(state, curr_task, tasks, plan, depth, calling_stack, methods):
        if not methods or len(methods) <= 1:
            return methods
        
        valid_methods = []
        infinite_methods = []

        for method in methods:
            subtasks = pyhop.get_subtasks(method, state, curr_task)

            # Keep failed subtasks in the valid list to let Pyhop handle the failure naturally
            if subtasks is False:
                valid_methods.append(method)
                continue

            is_infinite = False
            for subtask in subtasks:
                if subtask in calling_stack:
                    is_infinite = True
                    break
            
            # Separate the methods
            if not is_infinite:
                valid_methods.append(method)
            else:
                infinite_methods.append(method)
                
        # Return valid first, infinite last
        return valid_methods + infinite_methods
    pyhop.define_ordering(reorder_methods)

def set_up_state(data, ID):
	state = pyhop.State('state')
	setattr(state, 'time', {ID: data['Problem']['Time']})
	for item in data['Items']:
		setattr(state, item, {ID: 0})
	for item in data['Tools']:
		setattr(state, item, {ID: 0})
	for item, num in data['Problem']['Initial'].items():
		setattr(state, item, {ID: num})
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
	pyhop.pyhop(state, goals, verbose=1)

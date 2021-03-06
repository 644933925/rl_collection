import torch
import numpy as np

class Agent:
    def __init__(self, state_size, num_action, reward_discount, learning_rate, exploration_strategy):
        self.state_size = state_size
        self.num_action = num_action
        self.reward_discount = reward_discount
        self.exploration_strategy = exploration_strategy
        self.iter = 0
        self.eps = 0
        self.is_shutdown_explore = False

        self.data_type = torch.float32
        # self.optimizer = tf.keras.optimizers.Adam(learning_rate = learning_rate)
        # self.avg_loss = tf.keras.metrics.Mean(name = 'loss')
        self.model = self.build_model('model')

        # For A2C loss function coefficients
        self.coef_entropy = 0
        self.coef_value = 1

    def build_model(self, name):
        state_size = self.state_size
        num_action = self.num_action

        class Model(torch.nn.Module):
            def __init__(self):
                super(Model, self).__init__()
                self.model_inputs = torch.nn.Linear(state_size, 128)
                self.model_h1 = torch.nn.Linear(128, 128)
                self.model_actor_out = torch.nn.Linear(128, num_action)
                self.model_critic_out = torch.nn.Linear(128, 1)
            
            def forward(self, input):
                x = torch.nn.functional.relu(self.model_inputs(input))
                x = torch.nn.functional.relu(self.model_h1(x))
                actor_output = torch.nn.functional.softmax(self.model_actor_out(x), dim = 1)
                critic_output = torch.nn.functional.softmax(self.model_critic_out(x), dim = 1)

                return actor_output, critic_output

        return Model()

    def predict(self, state):
        return self.model.forward(torch.tensor(state, dtype = self.data_type))

    def loss(self, action_probs, critic_values, rewards):
        # Calculate accumulated reward Q(s, a) with discount
        np_rewards = np.array(rewards)
        num_reward = np_rewards.shape[0]
        discounts = np.logspace(0, num_reward, base = self.reward_discount, num = num_reward)
        
        q_values = np.zeros(num_reward)
        for i in range(num_reward):
            q_values[i] = np.sum(np.multiply(np_rewards[i:], discounts[:num_reward - i]))
        q_values = (q_values - np.mean(q_values)) / (np.std(q_values) + 1e-9)

        # Calculate the Actor Loss and Advantage A(s, a) = Q_value(s, a) - value(s)
        action_log_prbs = tf.math.log(action_probs)
        advs = q_values - critic_values
        actor_loss = -action_log_prbs * advs
        
        
        # Calculate the critic loss 
        huber = torch.nn.SmoothL1Loss()
        critic_loss = huber(torch.tensor(critic_values, dtype = self.data_type), torch.tensor(q_values, dtype = self.data_type))

        # Calculate the cross entropy of action distribution
        entropy = torch.sum(action_probs * action_log_prbs * -1)
        
        # Compute loss as formular: loss = Sum of a trajectory(-log(Pr(s, a| Theta)) * Advantage + coefficient of value * Value - coefficient of entropy * cross entropy of action distribution)
        # Advantage: A(s, a) = Q_value(s, a) - value(s)
        # The modification refer to the implement of Baseline A2C from OpenAI
        # Update model with a trajectory Every time.
        return torch.sum(actor_loss + self.coef_value * critic_loss - self.coef_entropy * entropy)

    def get_metrics_loss(self):
        pass
        # return self.avg_loss.result()
    
    def reset_metrics_loss(self):
        pass
        # self.avg_loss.reset_states()

    def select_action(self, state):
        # Predict the probability of each action(Stochastic Policy)
        act_dist, value = self.predict([state])
        act_dist = torch.squeeze(act_dist)
        value = torch.squeeze(value)
        # Assume using Epsilon Greedy Strategy
        action = self.exploration_strategy.select_action()
        
        # If the index of action (return value) is -1, choose the action with highest probability that model predict
#         if action == -1 or self.shutdown_explore == True:
#             # Pick then action with HIGHTEST probability
#             act_idx = tf.argmax(act_dist, axis = 0).numpy()
#             return act_idx, act_dist, value
#         else:
#             # If the index of action (return value) is != -1, act randomly    
#             return action, act_dist, value
        return np.random.choice(self.num_action, p=np.squeeze(act_dist.detach().numpy())), act_dist, value

    def shutdown_explore(self):
        self.is_shutdown_explore = True
        self.exploration_strategy.shutdown_explore()

    def __get_gradients(self, loss, tape, cal_gradient_vars):
        return tape.gradient(loss, cal_gradient_vars)

    def update(self, loss, gradients, apply_gradient_vars = None):
        if apply_gradient_vars == None:
            apply_gradient_vars = self.model.trainable_variables
#         Worker.lock.acquire()
        self.optimizer.apply_gradients(zip(gradients, apply_gradient_vars))
        self.avg_loss.update_state(loss)
#         Worker.lock.release()

        # Update exploration rate of Epsilon Greedy Strategy
        self.exploration_strategy.update_epsilon()

        self.iter += 1
        self.eps += 1

    def train_on_env(self, env, is_show = False, cal_gradient_vars = None):
        # By default, update agent's own trainable variables
        if cal_gradient_vars == None:
            cal_gradient_vars = self.model.trainable_variables
#         if apply_gradient_vars == None:
#             apply_gradient_vars = self.model.trainable_variables
            
        with tf.GradientTape() as tape:
            tape.watch(cal_gradient_vars)
            episode_reward = 0
            state = env.reset(is_show)

            action_probs = []
            critic_values = []
            rewards = []
            trajectory = []

            while not env.is_over():
                # env.render()
                action, act_prob_dist, value = self.select_action(state)

                act_prob = act_prob_dist[action]
                state_prime, reward, is_done, info = env.act(action)
                # print(f'State: {state}, Action: {action}, Reward: {reward}, State_Prime: {state_prime}')
                
                action_probs.append(act_prob)
                critic_values.append(value)
                rewards.append(reward)
                trajectory.append({'state': state, 'action': action, 'reward': reward, 'state_prime': state_prime, 'is_done': is_done})

                state = state_prime
                episode_reward += reward

            loss = self.loss(action_probs, critic_values, rewards)
            gradients = self.__get_gradients(loss, tape, cal_gradient_vars)
#             self.update(gradients, apply_gradient_vars)
            env.reset()

            return episode_reward, loss, gradients, trajectory

# if __name__ == '__main__':
    
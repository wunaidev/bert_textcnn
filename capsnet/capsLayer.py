import tensorflow as tf
import numpy as np


epsilon = 1e-9

class CapsLayer():

	def __init__(self, num_outputs, vec_len, layer_type='FC', with_routing=True, bz=8):
		self.num_outputs = num_outputs
		self.vec_len = vec_len
		self.layer_type = layer_type
		self.with_routing = with_routing
		self.bz = bz

	def __call__(self, input, kernel_size=None, stride=None):
		'''
		The parameters 'kernel_size' and 'stride' will be used while 'layer_type' equals 'CONV'
		'''
		if self.layer_type == 'CONV':
			self.kernel_size = kernel_size
			self.stride = stride

			if not self.with_routing:
				capsules = tf.layers.conv1d(input, filters=self.num_outputs * self.vec_len,
											kernel_size=self.kernel_size, strides=self.stride, padding='VALID',
											activation=tf.nn.relu)
				print("conv capsule shape: {}".format(capsules.shape))
				print("into turple shape: {}".format((self.bz, -1, self.vec_len, 1)))
				capsules = tf.reshape(capsules, (self.bz, -1, self.vec_len, 1))
				capsules = squash(capsules)

				return capsules

		if self.layer_type == 'FC':
			if self.with_routing:
				# the DigitCaps layer, a fully connected layer
				# Reshape the input into [batch_size, 1152, 1, 8, 1]
				self.input = tf.reshape(input, shape=(self.bz, -1, 1, input.shape[-2].value, 1))

				with tf.variable_scope('routing'):
					print("b_IJ tensor shape: {}".format([self.bz, input.shape[1], self.num_outputs, 1, 1]))
					#b_IJ = tf.constant(np.zeros([self.bz, input.shape[1].value, self.num_outputs, 1, 1], dtype=np.float32))
					b_IJ = tf.constant(np.zeros([8, input.shape[1], self.num_outputs, 1, 1], dtype=np.float32))
					#  (input.shape[1].value)��ֵ��max_seq_len * 16
					capsules = routing(self.input, b_IJ, max_seq_len_mul_16=input.shape[1].value, bz=self.bz)
					capsules = tf.squeeze(capsules, axis=1)

			return capsules


def routing(input, b_IJ, max_seq_len_mul_16, bz=8):
	W = tf.get_variable('Weight', shape=(1,max_seq_len_mul_16,4,8,16), dtype=tf.float32,     # * **
						initializer=tf.random_normal_initializer(stddev=0.01))
	biases = tf.get_variable('bias', shape=(1,1,1,16,1))

	input = tf.tile(input, [1,1,4,1,1])    # **
	W = tf.tile(W, [bz,1,1,1,1])

	u_hat = tf.matmul(W, input, transpose_a=True)

	u_hat_stopped = tf.stop_gradient(u_hat, name='stop_gradient')

	iter_routing = 3

	for r_iter in range(iter_routing):
		with tf.variable_scope('iter_' + str(r_iter)):
			c_IJ = tf.nn.softmax(b_IJ, dim=2)

			if r_iter == iter_routing - 1:
				s_J = tf.multiply(c_IJ, u_hat)
				s_J = tf.reduce_sum(s_J, axis=1, keep_dims=True) + biases

				v_J = squash(s_J)

			elif r_iter < iter_routing - 1:
				s_J = tf.multiply(c_IJ, u_hat_stopped)
				s_J = tf.reduce_sum(s_J, axis=1, keep_dims=True) + biases
				v_J = squash(s_J)

				v_J_tiled = tf.tile(v_J, [1,max_seq_len_mul_16,1,1,1])   #*
				u_produce_v = tf.matmul(u_hat_stopped, v_J_tiled, transpose_a=True)

				b_IJ += u_produce_v

	return v_J


def squash(x):
	squared_norm = tf.reduce_sum(tf.square(x), -2, keep_dims=True)
	scale = squared_norm / (1 + squared_norm) / tf.sqrt(squared_norm + epsilon)
	v = scale * x
	return v
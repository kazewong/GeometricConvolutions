import sys
sys.path.insert(0,'src/geometricconvolutions/')

import math
import itertools as it

from geometric import GeometricImage, Ktensor
import pytest
import jax.numpy as jnp
from jax import random

TINY = 1.e-5

def levi_civita_contract_old(ktensor_obj, index):
        assert ktensor_obj.D in [2, 3] # BECAUSE WE SUCK
        assert (ktensor_obj.k + 1) >= ktensor_obj.D # so we have enough indices work on
        if ktensor_obj.D == 2 and not isinstance(index, tuple):
            index = (index,)

        if ktensor_obj.D == 2:
            index = index[0]
            otherdata = jnp.zeros_like(ktensor_obj.data)
            otherdata = otherdata.at[..., 0].set(-1. * jnp.take(ktensor_obj.data, 1, axis=index))
            otherdata = otherdata.at[..., 1].set(1. * jnp.take(ktensor_obj.data, 0, axis=index)) #i swapped the -1 and 1
            return Ktensor(otherdata, ktensor_obj.parity + 1, ktensor_obj.D)
        if ktensor_obj.D == 3:
            assert len(index) == 2
            i, j = index
            assert i < j
            otherdata = jnp.zeros_like(ktensor_obj.data[..., 0])
            otherdata = otherdata.at[..., 0].set(jnp.take(jnp.take(ktensor_obj.data, 2, axis=j), 1, axis=i) \
                              - jnp.take(jnp.take(ktensor_obj.data, 1, axis=j), 2, axis=i))
            otherdata = otherdata.at[..., 1].set(jnp.take(jnp.take(ktensor_obj.data, 0, axis=j), 2, axis=i) \
                              - jnp.take(jnp.take(ktensor_obj.data, 2, axis=j), 0, axis=i))
            otherdata = otherdata.at[..., 2].set(jnp.take(jnp.take(ktensor_obj.data, 1, axis=j), 0, axis=i) \
                              - jnp.take(jnp.take(ktensor_obj.data, 0, axis=j), 1, axis=i))
            return Ktensor(otherdata, ktensor_obj.parity + 1, ktensor_obj.D)
        return

class TestGeometricImage:

    def testConstructor(self):
        #note we are not actually relying on randomness in this function, just filling values
        key = random.PRNGKey(0)

        image1 = Ktensor(jnp.array([5]), 0, 2)
        assert image1.data.shape == (1,)
        assert image1.k == 0
        assert image1.parity == 0

        image2 = Ktensor(jnp.array([1,1]), 1, 2)
        assert image2.data.shape == (2,)
        assert image2.D == 2
        assert image2.k == 1
        assert image2.parity == 1

        image3 = Ktensor(random.uniform(key, shape=(2,2)), 3, 2)
        assert image3.data.shape == (2,2)
        assert image3.D == 2
        assert image3.k == 2
        assert image3.parity == 1

        image4 = Ktensor(random.uniform(key, shape=(2,2,2)), 1, 2)
        assert image4.data.shape == (2,2,2)
        assert image4.D == 2
        assert image4.k == 3
        assert image4.parity == 1

        #D does not match dimensions
        with pytest.raises(AssertionError):
            Ktensor(random.uniform(key, shape=(10,10)), 0, 3)

        #non square
        with pytest.raises(AssertionError):
            GeometricImage(random.uniform(key, shape=(10,20)), 0, 10)

    def testAdd(self):
        ktensor1 = Ktensor(jnp.ones((2,2,2), dtype=int), 0, 2)
        ktensor2 = Ktensor(5*jnp.ones((2,2,2), dtype=int), 0, 2)

        result = ktensor1 + ktensor2
        assert (result.data == 6).all()
        assert result.parity == ktensor1.parity == ktensor2.parity
        assert result.D == ktensor1.D == ktensor2.D
        assert result.k == ktensor1.k == ktensor2.k

        assert (ktensor1.data == 1).all()
        assert (ktensor2.data == 5).all()

        ktensor3 = Ktensor(jnp.ones((3,3,3)), 0, 3)
        ktensor4 = Ktensor(jnp.ones((2,2,2)), 1, 2)
        ktensor5 = Ktensor(jnp.ones((2,2)), 0, 2)

        with pytest.raises(AssertionError): #D not equal
            result = ktensor1 + ktensor3

        with pytest.raises(AssertionError): #parity not equal
            result = ktensor1 + ktensor4

        with pytest.raises(AssertionError): #k not equal
            result = ktensor1 + ktensor5 #k

    def testTimeScalar(self):
        ktensor1 = Ktensor(jnp.ones((2,2,2), dtype=int), 0, 2)
        assert (ktensor1.data == 1).all()

        result = ktensor1.times_scalar(5)
        assert (result.data == 5).all()
        assert result.parity == ktensor1.parity
        assert result.D == ktensor1.D
        assert result.k == ktensor1.k
        assert (ktensor1.data == 1).all() #original is unchanged

        result2 = ktensor1.times_scalar(3.4)
        assert (result2.data == 3.4).all()
        assert (ktensor1.data == 1).all()

    def testGetItem(self):
        #note we are not actually relying on randomness in this function, just filling values
        key = random.PRNGKey(0)

        random_vals = random.uniform(key, shape=(4,4,4))
        image1 = Ktensor(random_vals, 0, 4)

        assert image1[0,1,1] == random_vals[0,1,1]
        assert image1[0,0,1] == random_vals[0,0,1]
        assert (image1[0] == random_vals[0]).all()
        assert (image1[1:,2:3] == random_vals[1:,2:3]).all()
        assert image1[1:, 2:3].shape == random_vals[1:, 2:3].shape

    # def testNormalize(self):
    #     key = random.PRNGKey(0)
    #     image1 = GeometricImage(random.uniform(key, shape=(10,10)), 0, 2)

    #     normed_image1 = image1.normalize()
    #     assert math.isclose(jnp.max(jnp.abs(normed_image1.data)), 1.)
    #     assert image1.data.shape == normed_image1.data.shape == (10,10)

    #     image2 = GeometricImage(random.uniform(key, shape=(10,10,2)), 0, 2)
    #     normed_image2 = image2.normalize()
    #     assert image2.data.shape == normed_image2.data.shape == (10,10,2)
    #     for row in normed_image2.data:
    #         for pixel in row:
    #             assert jnp.linalg.norm(pixel) < (1 + TINY)

    #     image3 = GeometricImage(random.uniform(key, shape=(10,10,2,2)), 0, 2)
    #     normed_image3 = image3.normalize()
    #     assert image3.data.shape == normed_image3.data.shape == (10,10,2,2)
    #     for row in normed_image3.data:
    #         for pixel in row:
    #             assert jnp.linalg.norm(pixel) < (1 + TINY)


    def testDotProduct(self):
        a = Ktensor(jnp.array([0,1,3]), 0, 3)
        b = Ktensor(jnp.array([1,2,-1]), 0, 3)

        ab = (a*b)
        dot = ab.contract(0,1)
        assert dot.data == -1
        assert dot.parity == ab.parity == a.parity == b.parity #in this case, since a and b have parity 1
        assert dot.D == ab.D
        assert dot.k == ab.k - 2

    def testCrossProduct(self):
        a = Ktensor(jnp.array([0,1,3]), 0, 3)
        b = Ktensor(jnp.array([1,2,-1]), 0, 3)

        ab = a*b
        cross = ab.levi_civita_contract((0,1))
        assert (cross.data == jnp.array([-7,3,-1])).all()
        assert cross.parity == (ab.parity + 1) % 2
        assert cross.D == ab.D == a.D == b.D
        assert cross.k == (ab.k - ab.D + 2)

    def testLeviCivitaContract(self):
        key = random.PRNGKey(0)

        for D in range(2,4):
            for k in range(D-1, D+2):
                key, subkey = random.split(key)
                ktensor1 = Ktensor(random.uniform(subkey, shape=k*(D,)), 0, D)

                for indices in it.combinations(range(k), D-1):
                    ktensor1_contracted = ktensor1.levi_civita_contract(indices)
                    assert (ktensor1_contracted.data == levi_civita_contract_old(ktensor1, indices).data).all()
                    assert ktensor1_contracted.k == (ktensor1.k - ktensor1.D + 2)
                    assert ktensor1_contracted.parity == (ktensor1.parity + 1) % 2
                    assert ktensor1_contracted.D == ktensor1.D

    def testTimesGroupElement(self):
        a = Ktensor(jnp.array([2,1], dtype=int), 0, 2)

        x_reflection = jnp.array([[1, 0], [0, -1]], dtype=int)
        y_reflection = jnp.array([[-1, 0], [0, 1]], dtype=int)
        counterclockwise_rotation = jnp.array([[0, -1], [1, 0]], dtype=int)

        assert jnp.allclose(a.times_group_element(x_reflection).data, jnp.array([2, -1], dtype=int))
        assert jnp.allclose(a.times_group_element(y_reflection).data, jnp.array([-2, 1], dtype=int))
        assert jnp.allclose(a.times_group_element(counterclockwise_rotation).data, jnp.array([-1, 2], dtype=int))




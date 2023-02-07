import pytest

import jax.numpy as jnp
from jax import random

import geometricconvolutions.geometric as geom

class TestBatchGeometricImage:

    def testConstructor(self):
        #note we are not actually relying on randomness in this function, just filling values
        key = random.PRNGKey(0)

        image1 = geom.BatchGeometricImage(random.uniform(key, shape=(1,10,10)), 0, 2)
        assert image1.data.shape == (1,10,10)
        assert image1.L == 1
        assert image1.D == 2
        assert image1.k == 0

        image2 = geom.BatchGeometricImage(random.uniform(key, shape=(20,10,10)), 0, 2)
        assert image2.data.shape == (20,10,10)
        assert image2.L == 20
        assert image2.D == 2
        assert image2.k == 0

        #Forgot that we need an L at the beginning, it won't be square
        with pytest.raises(AssertionError):
            geom.BatchGeometricImage(random.uniform(key, shape=(10,10,2)), 0, 3)

    def testEqual(self):
        img1 = geom.BatchGeometricImage(jnp.ones((5,10,10,2)), 0, 2)

        # same
        img2 = geom.BatchGeometricImage(jnp.ones((5,10,10,2)), 0, 2)
        assert img1 == img2

        # different L
        img3 = geom.BatchGeometricImage(jnp.ones((7,10,10,2)), 0, 2)
        assert img1 != img3

    def testAdd(self):
        image1 = geom.BatchGeometricImage(jnp.ones((5,10,10,2), dtype=int), 0, 2)
        image2 = geom.BatchGeometricImage(5*jnp.ones((5,10,10,2), dtype=int), 0, 2)
        float_image = geom.BatchGeometricImage(3.4*jnp.ones((5,10,10,2)), 0, 2)

        result = image1 + image2
        assert (result.data == 6).all()
        assert result.parity == 0
        assert result.D == 2
        assert result.k == 1
        assert result.N == 10
        assert result.L == 5

        assert (image1.data == 1).all()
        assert (image2.data == 5).all()

        result = image1 + float_image
        assert (result.data == 4.4).all()

        image3 = geom.BatchGeometricImage(jnp.ones((20,10,10,2), dtype=int), 0, 2)
        with pytest.raises(AssertionError): #L not equal
            result = image1 + image3

    def testSub(self):
        image1 = geom.BatchGeometricImage(jnp.ones((5,10,10,2), dtype=int), 0, 2)
        image2 = geom.BatchGeometricImage(5*jnp.ones((5,10,10,2), dtype=int), 0, 2)
        float_image = geom.BatchGeometricImage(3.4*jnp.ones((5,10,10,2)), 0, 2)

        result = image1 - image2
        assert (result.data == -4).all()
        assert result.parity == 0
        assert result.D == 2
        assert result.k == 1
        assert result.N == 10

        assert (image1.data == 1).all()
        assert (image2.data == 5).all()

        result = image1 - float_image
        assert (result.data == -2.4).all()

        image3 = geom.BatchGeometricImage(jnp.ones((20,10,10,2), dtype=int), 0, 2)
        with pytest.raises(AssertionError): #L not equal
            result = image1 - image3

    def testMul(self):
        image1 = geom.BatchGeometricImage(2*jnp.ones((10,3,3), dtype=int), 0, 2)
        image2 = geom.BatchGeometricImage(5*jnp.ones((10,3,3), dtype=int), 0, 2)

        mult1_2 = image1 * image2
        assert mult1_2.k == 0
        assert mult1_2.parity == 0
        assert mult1_2.D == image1.D == image2.D
        assert mult1_2.N == image1.N == image1.N
        assert mult1_2.L == image1.L == image2.L
        assert (mult1_2.data == 10*jnp.ones((3,3))).all()
        assert (mult1_2.data == (image2 * image1).data).all()

        image3 = geom.BatchGeometricImage(jnp.ones((5,3,3), dtype=int), 0, 2)

        with pytest.raises(AssertionError): #L not equal
            image1 * image3

    def testMaxPool(self):
        image1 = geom.GeometricImage(
            jnp.array([
                [4,1,0,1], 
                [0,0,-3,2], 
                [1,0,1,0],
                [1,0,2,1],
            ], dtype=float),
            0,
            2,
        )
        image2 = geom.GeometricImage(jnp.arange(4 ** 2).reshape((4,4)), 0, 2)

        batch_image = geom.BatchGeometricImage.from_images([image1, image2])

        batch_image_pool2 = batch_image.max_pool(2)
        assert batch_image_pool2.N == 2
        assert batch_image_pool2.parity == 0
        assert batch_image_pool2.D == 2
        assert batch_image_pool2.k == 0
        assert batch_image_pool2.is_torus == True
        assert batch_image_pool2.L == 2
        assert batch_image_pool2 == geom.BatchGeometricImage(
            jnp.array([
                [[4,-3],[1,2]],
                [[5,7],[13,15]],
            ]),
            0,
            2,
        )

    def testAveragePool(self):
        image1 = geom.GeometricImage(
            jnp.array([
                [4,1,0,1], 
                [0,0,-3,2], 
                [1,0,1,0],
                [1,0,2,1],
            ], dtype=float),
            0,
            2,
        )
        image2 = geom.GeometricImage(jnp.arange(4 ** 2).reshape((4,4)), 0, 2)

        batch_image = geom.BatchGeometricImage.from_images([image1, image2])

        batch_image_pool2 = batch_image.average_pool(2)
        assert batch_image_pool2.N == 2
        assert batch_image_pool2.parity == 0
        assert batch_image_pool2.D == 2
        assert batch_image_pool2.k == 0
        assert batch_image_pool2.is_torus == True
        assert batch_image_pool2.L == 2
        assert batch_image_pool2 == geom.BatchGeometricImage(
            jnp.array([
                [[1.25,0],[0.5,1]],
                [[2.5,4.5],[10.5,12.5]],
            ]),
            0,
            2,
        )
        
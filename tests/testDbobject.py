import os
import sqlite3

import unittest, numpy
import lsst.utils.tests as utilsTests
from lsst.sims.catalogs.generation.db import DBObject, ObservationMetaData
from lsst.sims.catUtils.observationMetadataUtils import haversine
import lsst.sims.catalogs.generation.utils.testUtils as tu

# This test should be expanded to cover more of the framework
# I have filed CATSIM-90 for this.

def createNonsenseDB():
    """
    Create a database from generic data store in testData/CatalogsGenerationTestData.txt
    This will be used to make sure that circ_bounds and box_bounds yield the points
    they are supposed to.
    """
    if os.path.exists('NonsenseDB.db'):
        os.unlink('NonsenseDB.db')
    
    conn = sqlite3.connect('NonsenseDB.db')
    c = conn.cursor()
    try:
        c.execute('''CREATE TABLE test (id int, ra real, dec real, mag real)''')
        conn.commit()
    except:
        raise RuntimeError("Error creating database.")
    
    inFile = open('testData/CatalogsGenerationTestData.txt','r')
    for line in inFile:
        values = line.split()
        cmd = '''INSERT INTO test VALUES (%s, %s, %s, %s)''' % (values[0],values[1],values[2],values[3])
        c.execute(cmd)
    
    conn.commit()
    conn.close()
    inFile.close()
    
class myNonsenseDB(DBObject):
    objid = 'Nonsense'
    tableid = 'test'
    idColKey = 'NonsenseId'
    #Make this implausibly large?  
    dbAddress = 'sqlite:///NonsenseDB.db'
    raColName = 'ra'
    decColName = 'dec'
    columns = [('NonsenseId', 'id', int),
               ('NonsenseRaJ2000', 'ra*%f'%(numpy.pi/180.)),
               ('NonsenseDecJ2000', 'dec*%f'%(numpy.pi/180.)),
               ('NonsenseMag','mag',float)]


class DBObjectTestCase(unittest.TestCase):
  
    #Delete the test database if it exists and start fresh.
    if os.path.exists('testDatabase.db'):
        print "deleting database"
        os.unlink('testDatabase.db')
    tu.makeStarTestDB(size=100000, seedVal=1)
    tu.makeGalTestDB(size=100000, seedVal=1)
    createNonsenseDB()
    obsMd = ObservationMetaData(circ_bounds=dict(ra=210., dec=-60, radius=1.75),
                                     mjd=52000., bandpassName='r')
    
    inFile = open('testData/CatalogsGenerationTestData.txt','r')
    
    """
    baselineData will store another copy of the data that should be stored in
    NonsenseDB.db.  This will give us something to test database queries against
    when we ask for all of the objects within a certain box_bounds or circ_bounds.
    """
    baselineData=None
    for line in inFile:
        values=line.split()
            
        if baselineData is None:
            baselineData = numpy.array([(int(values[0]),float(values[1]),
                                           float(values[2]),float(values[3]))], \
                                       dtype=[('id',int),('ra',float),('dec',float),('mag',float)])
        else:
            baselineData = numpy.append(baselineData,numpy.array([(int(values[0]),float(values[1]),
                                                                 float(values[2]),float(values[3]))],
                                                          dtype=baselineData.dtype))  
    inFile.close()
    
    def testObsMD(self):
        self.assertEqual(self.obsMd.bandpass, 'r')
        self.assertAlmostEqual(self.obsMd.mjd, 52000., 6)
    
    def testDbObj(self):
        mystars = DBObject.from_objid('teststars')
        mygals = DBObject.from_objid('testgals')
        result = mystars.query_columns(obs_metadata=self.obsMd)
        tu.writeResult(result, "/dev/null")
        result = mystars.query_columns(obs_metadata=self.obsMd)
        tu.writeResult(result, "/dev/null")

    def testRealQueryConstraints(self):
        mystars = DBObject.from_objid('teststars')
        mycolumns = ['id','raJ2000','decJ2000','umag','gmag','rmag','imag','zmag','ymag']
        
        #recall that ra and dec are stored in degrees in the data base
        myquery = mystars.query_columns(colnames = mycolumns, 
                                        constraint = 'ra < 90. and ra > 45.')
        
        tol=1.0e-3
        for chunk in myquery:
            for star in chunk:
                self.assertTrue(numpy.degrees(star[1])<90.0+tol)
                self.assertTrue(numpy.degrees(star[1])>45.0-tol)
    
    def testNonsenseCircularConstraints(self):
        """
        Test that a query performed on a circ_bounds gets all of the objects (and only all
        of the objects) within that circle
        """
        
        myNonsense = DBObject.from_objid('Nonsense')
        
        radius = 20.0
        raCenter = 210.0
        decCenter = -60.0
        
        mycolumns = ['NonsenseId','NonsenseRaJ2000','NonsenseDecJ2000','NonsenseMag']
        
        circObsMd = ObservationMetaData(circ_bounds=dict(ra=raCenter, dec=decCenter, radius=radius),
                                     mjd=52000., bandpassName='r')
       
        circQuery = myNonsense.query_columns(colnames = mycolumns, obs_metadata=circObsMd, chunk_size=100)
        
        raCenter = numpy.radians(raCenter)
        decCenter = numpy.radians(decCenter)
        radius = numpy.radians(radius)

        goodPoints = []

        for chunk in circQuery:
            for row in chunk:
                distance = haversine(raCenter,decCenter,row[1],row[2])
          
                self.assertTrue(distance<radius)
                
                dex = numpy.where(self.baselineData['id'] == row[0])[0][0]
                
                #store a list of which objects fell within our circ_bounds
                goodPoints.append(row[0])
                
                self.assertAlmostEqual(numpy.radians(self.baselineData['ra'][dex]),row[1],3)
                self.assertAlmostEqual(numpy.radians(self.baselineData['dec'][dex]),row[2],3)
                self.assertAlmostEqual(self.baselineData['mag'][dex],row[3],3)
                

        for entry in [xx for xx in self.baselineData if xx[0] not in goodPoints]:
            #make sure that all of the points not returned by the query were, in fact, outside of
            #the circ_bounds
            distance = haversine(raCenter,decCenter,numpy.radians(entry[1]),numpy.radians(entry[2]))
            self.assertTrue(distance>radius)
    
   
    def testNonsenseSelectOnlySomeColumns(self):
        """
        Test a query performed only a subset of the available columns
        """
        myNonsense = DBObject.from_objid('Nonsense')
     
        mycolumns = ['NonsenseId','NonsenseRaJ2000','NonsenseMag']
       
        query = myNonsense.query_columns(colnames=mycolumns, constraint = 'ra < 45.', chunk_size=100)

        goodPoints = []

        for chunk in query:
            for row in chunk:
                self.assertTrue(row[1]<45.0)
                
                dex = numpy.where(self.baselineData['id'] == row[0])[0][0]
                
                goodPoints.append(row[0])
                
                self.assertAlmostEqual(numpy.radians(self.baselineData['ra'][dex]),row[1],3)
                self.assertAlmostEqual(self.baselineData['mag'][dex],row[2],3)
                

        for entry in [xx for xx in self.baselineData if xx[0] not in goodPoints]:
            self.assertTrue(entry[1]>45.0)

    def testNonsenseBoxConstraints(self):
        """
        Test that a query performed on a box_bounds gets all of the points (and only all of the
        points) inside that box_bounds.
        """
        
        myNonsense = DBObject.from_objid('Nonsense')
    
        raMin = 50.0
        raMax = 150.0
        decMax = 30.0
        decMin = -20.0
        
        mycolumns = ['NonsenseId','NonsenseRaJ2000','NonsenseDecJ2000','NonsenseMag']
     
        boxObsMd = ObservationMetaData(box_bounds=dict(ra_min=raMin, ra_max=raMax, 
                                       dec_min=decMin, dec_max=decMax), mjd=52000.,bandpassName='r')
        
        boxQuery = myNonsense.query_columns(obs_metadata=boxObsMd, chunk_size=100, colnames=mycolumns)
       
        raMin = numpy.radians(raMin)
        raMax = numpy.radians(raMax)
        decMin = numpy.radians(decMin)
        decMax = numpy.radians(decMax)

        goodPoints = []
        
        for chunk in boxQuery:
            for row in chunk:
                self.assertTrue(row[1]<raMax)
                self.assertTrue(row[1]>raMin)
                self.assertTrue(row[2]<decMax)
                self.assertTrue(row[2]>decMin)
          
                dex = numpy.where(self.baselineData['id'] == row[0])[0][0]
                
                #keep a list of which points were returned by teh query
                goodPoints.append(row[0])
                
                self.assertAlmostEqual(numpy.radians(self.baselineData['ra'][dex]),row[1],3)
                self.assertAlmostEqual(numpy.radians(self.baselineData['dec'][dex]),row[2],3)
                self.assertAlmostEqual(self.baselineData['mag'][dex],row[3],3)
      
        for entry in [xx for xx in self.baselineData if xx[0] not in goodPoints]:
            #make sure that the points not returned by the query are, in fact, outside of the
            #box_bounds
            
            switch = (entry[1] > raMax or entry[1] < raMin or entry[2] >decMax or entry[2] < decMin)
            self.assertTrue(switch)

    def testNonsenseArbitraryConstraints(self):
        """
        Test a query with a user-specified constraint on the magnitude column
        """
    
        myNonsense = DBObject.from_objid('Nonsense')
    
        raMin = 50.0
        raMax = 150.0
        decMax = 30.0
        decMin = -20.0
        
        mycolumns = ['NonsenseId','NonsenseRaJ2000','NonsenseDecJ2000','NonsenseMag']
     
        boxObsMd = ObservationMetaData(box_bounds=dict(ra_min=raMin, ra_max=raMax, 
                                       dec_min=decMin, dec_max=decMax), mjd=52000.,bandpassName='r')
        
        boxQuery = myNonsense.query_columns(colnames = mycolumns,
                      obs_metadata=boxObsMd, chunk_size=100, constraint = 'mag > 11.0')
       
        raMin = numpy.radians(raMin)
        raMax = numpy.radians(raMax)
        decMin = numpy.radians(decMin)
        decMax = numpy.radians(decMax)

        goodPoints = []

        for chunk in boxQuery:
            for row in chunk:
              
                self.assertTrue(row[1]<raMax)
                self.assertTrue(row[1]>raMin)
                self.assertTrue(row[2]<decMax)
                self.assertTrue(row[2]>decMin)
                self.assertTrue(row[3]>11.0)
          
                dex = numpy.where(self.baselineData['id'] == row[0])[0][0]
                
                #keep a list of the points returned by the query
                goodPoints.append(row[0])
                
                self.assertAlmostEqual(numpy.radians(self.baselineData['ra'][dex]),row[1],3)
                self.assertAlmostEqual(numpy.radians(self.baselineData['dec'][dex]),row[2],3)
                self.assertAlmostEqual(self.baselineData['mag'][dex],row[3],3)
        
        for entry in [xx for xx in self.baselineData if xx[0] not in goodPoints]:
            #make sure that the points not returned by the query did, in fact, violate one of the
            #constraints of the query (either the box_bounds or the magnitude cut off)
            switch = (entry[1] > raMax or entry[1] < raMin or entry[2] >decMax or entry[2] < decMin or entry[3]<11.0)
            
            self.assertTrue(switch)
        
    def testChunking(self):
        """
        Test that a query with a specified chunk_size does, in fact, return chunks of that size
        """
        
        mystars = DBObject.from_objid('teststars')
        mycolumns = ['id','raJ2000','decJ2000','umag','gmag']
        myquery = mystars.query_columns(colnames = mycolumns, chunk_size = 1000)
        
        for chunk in myquery:
            self.assertEqual(chunk.size,1000)
            for row in chunk:
                self.assertTrue(len(row),5)
    
    def testClassVariables(self):
        """
        Make sure that the daughter classes of DBObject properly overwrite the member
        variables of DBObject
        """
        
        mystars = DBObject.from_objid('teststars')
        myNonsense = DBObject.from_objid('Nonsense')
        mygalaxies = DBObject.from_objid('testgals')
        
        self.assertEqual(mystars.raColName,'ra')
        self.assertEqual(mystars.decColName,'decl')
        self.assertEqual(mystars.idColKey,'id')
        self.assertEqual(mystars.dbAddress,'sqlite:///testDatabase.db')
        self.assertEqual(mystars.appendint, 1023)
        self.assertEqual(mystars.tableid,'stars')
        self.assertFalse(hasattr(mystars,'spatialModel'))
        self.assertEqual(mystars.objid,'teststars')
        
        self.assertEqual(mygalaxies.raColName,'ra')
        self.assertEqual(mygalaxies.decColName,'decl')
        self.assertEqual(mygalaxies.idColKey,'id')
        self.assertEqual(mygalaxies.dbAddress,'sqlite:///testDatabase.db')
        self.assertEqual(mygalaxies.appendint, 1022)
        self.assertEqual(mygalaxies.tableid,'galaxies')
        self.assertTrue(hasattr(mygalaxies,'spatialModel'))
        self.assertEqual(mygalaxies.spatialModel,'SERSIC2D')
        self.assertEqual(mygalaxies.objid,'testgals')
        
        self.assertEqual(myNonsense.raColName,'ra')
        self.assertEqual(myNonsense.decColName,'dec')
        self.assertEqual(myNonsense.idColKey,'NonsenseId')
        self.assertEqual(myNonsense.dbAddress,'sqlite:///NonsenseDB.db')
        self.assertFalse(hasattr(myNonsense,'appendint'))
        self.assertEqual(myNonsense.tableid,'test')
        self.assertFalse(hasattr(myNonsense,'spatialModel'))
        self.assertEqual(myNonsense.objid,'Nonsense')
        
        self.assertTrue('teststars' in DBObject.registry)
        self.assertTrue('testgals' in DBObject.registry)
        self.assertTrue('Nonsense' in DBObject.registry)
       
        colsShouldBe = [('id',None,int),('raJ2000','ra*%f'%(numpy.pi/180.)),
                        ('decJ2000','decl*%f'%(numpy.pi/180.)),
                        ('umag',None),('gmag',None),('rmag',None),('imag',None),
                        ('zmag',None),('ymag',None),
                        ('magNorm','mag_norm',float)]
                       
        for (col,coltest) in zip(mystars.columns,colsShouldBe):
            self.assertEqual(col,coltest)
        
        colsShouldBe = [('NonsenseId', 'id', int),
               ('NonsenseRaJ2000', 'ra*%f'%(numpy.pi/180.)),
               ('NonsenseDecJ2000', 'dec*%f'%(numpy.pi/180.)),
               ('NonsenseMag','mag',float)]
        
        for (col,coltest) in zip(myNonsense.columns,colsShouldBe):
            self.assertEqual(col,coltest)
                
        colsShouldBe = [('id', None, int),
               ('raJ2000', 'ra*%f'%(numpy.pi/180.)),
               ('decJ2000', 'decl*%f'%(numpy.pi/180.)),
               ('umag', None),
               ('gmag', None),
               ('rmag', None),
               ('imag', None),
               ('zmag', None),
               ('ymag', None),
               ('magNormAgn', 'mag_norm_agn', None),
               ('magNormDisk', 'mag_norm_disk', None),
               ('magNormBulge', 'mag_norm_bulge', None),
               ('redshift', None),
               ('a_disk', None),
               ('b_disk', None),
               ('a_bulge', None),
               ('b_bulge', None),]
            
        for (col,coltest) in zip(mygalaxies.columns,colsShouldBe):
            self.assertEqual(col,coltest)
            
def suite():
    """Returns a suite containing all the test cases in this module."""
    utilsTests.init()
    suites = []
    suites += unittest.makeSuite(DBObjectTestCase)
    suites += unittest.makeSuite(utilsTests.MemoryTestCase)

    return unittest.TestSuite(suites)

def run(shouldExit=False):
    """Run the tests"""
    utilsTests.run(suite(), shouldExit)

if __name__ == "__main__":
    run(True)
